"""Contract tests for public documentation that describes live behaviour.

These assertions are deliberately narrow. Prose in general is not executable,
but four statements here are interfaces: the benchmark table and measured
results are the advertised evaluation contract, run-id entropy is part of the
capability-URL security model, and the list of serving surfaces tells a new
contributor which entry points exist. All four have drifted while every runtime
test stayed green.
"""

from __future__ import annotations

import ast
import csv
import re
import tomllib
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

    @staticmethod
    def _binds_api_app(source: str) -> bool:
        for node in ast.parse(source).body:
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                targets = [node.target]
            else:
                continue
            if any(isinstance(target, ast.Name) and target.id == "app" for target in targets):
                return True
        return False

    def _check_launch_commands(self, text: str, *, module_docstring: bool = False) -> set[str]:
        # Inspect standalone launch examples, not every mention of a retired
        # product. "Gradio was removed" is useful history, not a broken command.
        # This is deliberately not a shell interpreter or general prose audit.
        surfaces = set()
        # Markdown fences and indented module-docstring examples identify code.
        # A prose sentence beginning with a product name is still only prose.
        examples = re.findall(r"^```[^\n]*\n(.*?)^```", text, re.MULTILINE | re.DOTALL)
        if module_docstring:
            examples.extend(line[4:] for line in text.splitlines() if line.startswith("    "))
        removed = (
            r"(?i)^(?:uv[ \t]+run[ \t]+)?"
            r"(?:python(?:3(?:\.\d+)?)?[ \t]+(?:-m[ \t]+)?)?"
            r"(?:gradio|(?:\./)?app\.py)(?:[ \t]|$)"
        )
        invalid_script = (
            r"(?i)^(?:uv[ \t]+run[ \t]+)?python(?:3(?:\.\d+)?)?[ \t]+"
            r"(?:uvicorn|academic_agent)(?:[ \t]|$)"
        )
        for line in "\n".join(examples).splitlines():
            command = line.strip()
            self.assertNotRegex(command, removed)
            # Never strip Python: `python uvicorn` executes a script, not the
            # installed command. Only the two documented uv forms count below.
            self.assertNotRegex(command, invalid_script)
            if re.match(r"uv[ \t]+run[ \t]+uvicorn(?:[ \t]|$)", command):
                self.assertRegex(command, r"^uv[ \t]+run[ \t]+uvicorn[ \t]+api\.main:app(?:[ \t]|$)")
                surfaces.add("web")
            elif re.match(r"uv[ \t]+run[ \t]+academic_agent(?:[ \t]|$)", command):
                self.assertRegex(command, r"^uv[ \t]+run[ \t]+academic_agent[ \t]+--topic[ \t]+\S+")
                surfaces.add("cli")
        return surfaces

    def test_current_entry_point_docs_use_existing_launch_targets(self):
        # Bind the advertised commands to actual package targets without
        # importing a serving entry point or starting a paid analysis.
        package = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(package["project"]["scripts"]["academic_agent"], "academic_agent.main:run")
        cli = ast.parse((ROOT / "src/academic_agent/main.py").read_text(encoding="utf-8"))
        self.assertTrue(any(isinstance(node, ast.FunctionDef) and node.name == "run" for node in cli.body))
        self.assertTrue(self._binds_api_app((ROOT / "api/main.py").read_text(encoding="utf-8")))
        for relative, expected in (
            ("README.md", {"web", "cli"}), ("README.zh-CN.md", {"web", "cli"}),
            ("AGENTS.md", {"web", "cli"}), ("CONTRIBUTING.md", set()),
            ("api/main.py", {"web"}), ("api/runs.py", set()), ("api/papers.py", set()),
        ):
            with self.subTest(file=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                if relative.endswith(".py"):
                    text = ast.get_docstring(ast.parse(text)) or ""
                self.assertTrue(expected <= self._check_launch_commands(
                    text, module_docstring=relative.endswith(".py"),
                ))

    def test_api_binding_allows_annotations_but_requires_a_value(self):
        """An equivalent typed assignment is live; an annotation alone binds nothing."""
        for source, expected in (
            ("app = FastAPI()", True), ("app: FastAPI = FastAPI()", True),
            ("app: FastAPI", False), ("other = FastAPI()", False),
        ):
            with self.subTest(source=source):
                self.assertEqual(self._binds_api_app(source), expected)

    def test_launch_contract_rejects_dead_commands_not_historical_prose(self):
        """Reinstate removed launch commands without forbidding valid history."""
        valid = (
            "Gradio was removed.\n    Gradio in indented prose is still history.\n"
            "```bash\n# python app.py is obsolete.\n"
            "uv run uvicorn api.main:app --reload\n"
            'uv run academic_agent --topic "example"\n```'
        )
        self.assertEqual(self._check_launch_commands(valid), {"web", "cli"})
        self.assertEqual(self._check_launch_commands(
            "    uv run uvicorn api.main:app --reload", module_docstring=True,
        ), {"web"})
        for command in (
            "python app.py", "uv run python app.py", "uv run app.py",
            "python -m gradio app.py", "gradio app.py",
            "uv run uvicorn app:app --reload",
            "python uvicorn api.main:app", "python academic_agent --topic x",
            "uv run python uvicorn api.main:app", "uv run python academic_agent --topic x",
        ):
            for is_docstring in (False, True):
                example = f"    {command}" if is_docstring else f"```bash\n{command}\n```"
                with self.subTest(command=command, docstring=is_docstring), self.assertRaises(AssertionError):
                    self._check_launch_commands(example, module_docstring=is_docstring)


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
