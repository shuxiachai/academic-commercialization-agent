"""Contract tests for public documentation that describes live behaviour.

These assertions are deliberately narrow. Prose in general is not executable,
but five statements here are interfaces: the benchmark table and measured
results are the advertised evaluation contract, run-id entropy is part of the
capability-URL security model, the list of serving surfaces tells a new
contributor which entry points exist, and the operating guide's contents list
maps its sections. The first four have drifted while every runtime test stayed
green; the fifth is held to the same standard before it can.
"""

from __future__ import annotations

import ast
import csv
import re
import tempfile
import tomllib
import unicodedata
import unittest
from pathlib import Path
from urllib.parse import unquote

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

    @staticmethod
    def _github_anchor(heading: str) -> str:
        """Return the anchor GitHub generates for one Markdown heading.

        GitHub lowercases the heading, drops punctuation (anything that is
        not a word character, a space or a hyphen), turns spaces into
        hyphens, and keeps non-ASCII letters such as Chinese characters.
        Inline Markdown is rendered first, so code spans, links and
        emphasis markers never reach the anchor.
        """
        text = re.sub(r"`([^`]*)`", r"\1", heading)
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
        text = re.sub(r"\[([^\]]*)\]\[[^\]]*\]", r"\1", text)
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("**", "").replace("__", "")
        text = re.sub(r"(?<!\w)\*|\*(?!\w)", "", text)
        text = re.sub(r"(?<!\w)_|_(?!\w)", "", text)
        slug = []
        for char in text.lower():
            if char == " ":
                slug.append("-")
            elif char in "-_" or char.isalnum() or unicodedata.category(char).startswith("M"):
                slug.append(char)
        return "".join(slug)

    @staticmethod
    def _anchors_in(document: Path) -> set[str]:
        """Anchors a Markdown file offers: heading slugs plus explicit ids.

        Headings inside fenced code blocks are not headings, and a repeated
        heading takes the ``-1`` / ``-2`` suffix GitHub appends. An explicit
        ``<a id="...">`` counts as well.
        """
        text = document.read_text(encoding="utf-8")
        text = re.sub(r"^```[^\n]*\n.*?^```", "", text, flags=re.MULTILINE | re.DOTALL)
        text = re.sub(r"^~~~[^\n]*\n.*?^~~~", "", text, flags=re.MULTILINE | re.DOTALL)
        anchors: set[str] = set()
        seen: dict[str, int] = {}
        for match in re.finditer(r"^#{1,6}\s+(.+?)\s*#*\s*$", text, flags=re.MULTILINE):
            slug = PublicDocumentationNavigationTests._github_anchor(match.group(1))
            if not slug:
                continue
            occurrence = seen.get(slug, 0)
            seen[slug] = occurrence + 1
            anchors.add(slug if occurrence == 0 else f"{slug}-{occurrence}")
        anchors.update(re.findall(r'<a\s+[^>]*\bid\s*=\s*["\']([^"\']+)["\']', text))
        return anchors

    def test_github_anchor_rules(self):
        """The anchor rules above must match GitHub, not a local guess.

        Covers the shapes the guides actually use — punctuation dropped,
        Chinese kept — plus the two the issue names and no guide happens to
        exercise yet: repeated headings and headings inside code blocks.
        """
        self.assertEqual(self._github_anchor("Web, CLI and HTTP API"), "web-cli-and-http-api")
        self.assertEqual(self._github_anchor("快速启动"), "快速启动")
        self.assertEqual(self._github_anchor("实测结果"), "实测结果")
        self.assertEqual(self._github_anchor("Don't (re)do these: v2.0!"), "dont-redo-these-v20")
        self.assertEqual(self._github_anchor("snake_case stays"), "snake_case-stays")
        with tempfile.TemporaryDirectory() as directory:
            document = Path(directory) / "guide.md"
            document.write_text(
                "## Setup\n\n```md\n## Setup\n```\n\n## Setup\n\n<a id=\"custom-anchor\"></a>\n",
                encoding="utf-8",
            )
            self.assertEqual(self._anchors_in(document), {"setup", "setup-1", "custom-anchor"})

    def test_current_guide_section_links_point_at_real_headings(self):
        """Every #section link into a Markdown file must match a heading.

        The file-existence test above drops everything after ``#``, so a
        renamed heading broke every link to it while the suite stayed
        green. A link with no fragment, or into a non-Markdown file, is out
        of scope here; a same-file ``#anchor`` link is checked against its
        own file. The failure names the file and the link, as the issue asks.
        """
        checked = 0
        anchors_by_file: dict[Path, set[str]] = {}
        for relative in (
            "README.md", "README.zh-CN.md", "AGENTS.md", "CONTRIBUTING.md",
            "docs/README.md", "docs/evidence-status.md", "docs/operating-guide.md",
            "docs/portfolio-case-study.md", "docs/experiment-index.md",
        ):
            document = ROOT / relative
            for target in re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
                if "#" not in target or "://" in target:
                    continue
                path, fragment = target.split("#", maxsplit=1)
                fragment = unquote(fragment)
                if not fragment:
                    continue
                linked = document if not path else document.parent / path
                if linked.suffix != ".md":
                    continue
                if linked not in anchors_by_file:
                    anchors_by_file[linked] = self._anchors_in(linked)
                with self.subTest(file=relative, target=target):
                    self.assertTrue(linked.is_file(), target)
                    self.assertIn(
                        fragment, anchors_by_file[linked],
                        f"{relative}: {target} points at no heading in {linked}",
                    )
                    checked += 1
        # Silence is not a pass: the guides carry dozens of section links,
        # so a run that checked none of them would be a broken check, not a
        # green one.
        self.assertGreater(checked, 0, "no #section links found to check")

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

    def test_current_guides_describe_root_python_files_and_entries_accurately(self):
        """Current guides must not claim root holds experiment runners, and entries match today's root."""
        readme_en = (ROOT / "README.md").read_text(encoding="utf-8")
        readme_zh = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")
        docs_readme = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")

        # No current guide should claim the root holds many Python files or experiment runners
        self.assertNotIn("many Python files at the root", readme_en)
        self.assertNotIn("Most of the Python files at the repository root", readme_en)
        self.assertNotIn("根目录下的大量 Python 文件", readme_zh)
        self.assertNotIn("根目录下的大多数 Python 文件", readme_zh)

        # Both READMEs agree that root holds the four benchmark commands and experiment runners live in experiments/
        self.assertRegex(
            readme_en,
            r"The four Python files at the\s+root are benchmark commands",
        )
        self.assertRegex(
            readme_en,
            r"frozen experiment runners live in\s+`experiments/`",
        )
        self.assertIn("根目录下的 4 个 Python 文件是基准测试命令", readme_zh)
        self.assertIn("已冻结的实验运行器位于 `experiments/`", readme_zh)

        # docs/README.md lists root entries including newer configuration, entry and metadata files
        for entry in (
            ".devcontainer/",
            "docker-entrypoint.sh",
            "CITATION.cff",
            "SECURITY.md",
        ):
            with self.subTest(entry=entry):
                self.assertIn(entry, docs_readme)


class OperatingGuideContentsTests(unittest.TestCase):
    """The operating guide's contents list must cover every section.

    The guide is about 2,100 lines long; without a list at the top a reader
    looking for one section has to scroll or search. A section added without
    a list entry is the same drift in miniature, so the list is held to the
    headings it claims to cover, in order and at the right depth.
    """

    GUIDE = ROOT / "docs" / "operating-guide.md"

    @staticmethod
    def _github_anchor(heading: str) -> str:
        # The anchor GitHub gives a heading: lowercase, punctuation dropped
        # except hyphens and underscores, spaces become hyphens.
        anchor = re.sub(r"[^\w\s-]", "", heading.lower())
        return re.sub(r"\s+", "-", anchor.strip())

    @staticmethod
    def _headings_and_contents(text: str) -> tuple[
        list[tuple[int, str, str]], list[tuple[int, str, str]]
    ]:
        headings: list[tuple[int, str, str]] = []
        contents: list[tuple[int, str, str]] = []
        in_fence = False
        first_section = False
        for line in text.splitlines():
            if line.strip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            match = re.match(r"^(#{2,3}) (.+)$", line)
            if match:
                first_section = True
                level = len(match.group(1))
                title = match.group(2)
                headings.append(
                    (level, title, OperatingGuideContentsTests._github_anchor(title))
                )
                continue
            if not first_section:
                entry = re.match(r"^( *)- \[(.+)\]\(#(.+)\)$", line)
                if entry:
                    level = len(entry.group(1)) // 2 + 2
                    contents.append((level, entry.group(2), entry.group(3)))
        return headings, contents

    def test_contents_list_covers_every_section_and_subsection(self):
        headings, contents = self._headings_and_contents(
            self.GUIDE.read_text(encoding="utf-8")
        )
        # An empty list would pass a "no missing entry" check the same way an
        # empty guide would; the guide has sections, so the list must too.
        self.assertGreater(len(headings), 0)
        self.assertEqual(contents, headings)


if __name__ == "__main__":
    unittest.main()
