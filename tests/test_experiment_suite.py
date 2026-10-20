"""The experiment list must only ever narrow CI for code the app does not run.

Pull-request CI skips `experiment`-marked tests on the Windows and Python 3.11
cells (tests/experiment_tests.txt). A listed file that actually exercised the
web app or the analysis pipeline would silently lose those cells, so every
listed file must be named after a module that neither imports.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

from conftest import experiment_test_files

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "academic_agent"
# Supported tools, not experiments: the benchmark's Windows spawn path is one
# reason the matrix includes Windows at all.
_SUPPORTED_TOOLS = ("benchmark", "ops_report")


def _static_imports(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("academic_agent"):
            if node.module == "academic_agent":
                names |= {alias.name for alias in node.names}
            else:
                names.add(node.module.rsplit(".", 1)[-1])
        elif isinstance(node, ast.Import):
            names |= {a.name.rsplit(".", 1)[-1] for a in node.names if a.name.startswith("academic_agent.")}
    return {name for name in names if (SRC / f"{name}.py").exists()}


def _production_modules() -> set[str]:
    """Modules the deployed app loads, plus everything the pipeline can import.

    Importing the entry points catches import-time use; the static closure from
    the pipeline catches collaborators imported lazily inside functions.
    """
    script = (
        "import sys\n"
        "import api.main, api.saved_source_production\n"
        "import academic_agent.pipeline_worker, academic_agent.crew, academic_agent.main\n"
        "import academic_agent.source_pipeline, academic_agent.evidence\n"
        "import ui.i18n, ui.run_reader, ui.pdf_export\n"
        "print('\\n'.join(sorted(m for m in sys.modules if m.startswith(('academic_agent', 'api', 'ui')))))\n"
    )
    loaded = subprocess.run(
        [sys.executable, "-c", script], cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", timeout=120, check=True,
        env={**os.environ, "OTEL_SDK_DISABLED": "true", "AGENT_OBSERVABILITY_ENABLED": "false"},
    ).stdout.split()
    closure, todo = set(), ["pipeline_worker", "crew", "main", "source_pipeline", "evidence"]
    while todo:
        name = todo.pop()
        if name in closure:
            continue
        closure.add(name)
        todo.extend(_static_imports(SRC / f"{name}.py") - closure)
    return {name.rsplit(".", 1)[-1] for name in loaded} | closure


def _target(test_file: str, modules: set[str]) -> str | None:
    stem = test_file.removeprefix("test_").removesuffix(".py")
    candidates = [m for m in modules if stem == m or stem.startswith(m + "_")]
    return max(candidates, key=len) if candidates else None


def test_list_names_existing_files_once():
    raw = [line.strip() for line in (ROOT / "tests" / "experiment_tests.txt").read_text(
        encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]
    assert raw == sorted(set(raw)), "Keep the list sorted and free of duplicates"
    for name in raw:
        assert (ROOT / "tests" / name).is_file(), name


def test_no_listed_file_targets_code_the_app_or_pipeline_runs():
    production = _production_modules()
    modules = (
        {p.stem for p in (ROOT / "src" / "academic_agent").rglob("*.py")}
        | {p.stem for p in (ROOT / "api").glob("*.py")}
        | {p.stem for p in ROOT.glob("*.py")}
        | {p.stem for p in (ROOT / "scripts").rglob("*.py")}
    ) - {"__init__"}
    for name in sorted(experiment_test_files()):
        target = _target(name, modules)
        assert target is not None, f"{name}: name it after the experiment module it tests"
        assert target not in production, f"{name} tests {target}, which the app or pipeline uses"
        assert not target.startswith(_SUPPORTED_TOOLS), f"{name} tests a supported tool"


def test_marker_selects_only_listed_files():
    """The real collection hook, not a re-implementation of it."""
    listed, unlisted = "test_openalex_precision.py", "test_language.py"
    assert listed in experiment_test_files() and unlisted not in experiment_test_files()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider",
         "-m", "experiment", f"tests/{listed}", f"tests/{unlisted}"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120, check=False,
    )
    selected = [line for line in result.stdout.splitlines() if "::" in line]
    assert selected, result.stdout + result.stderr
    assert all(line.startswith(f"tests/{listed}::") for line in selected)
