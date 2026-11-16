"""CrewAI's own usage reporting is off unless an operator turns it on.

CrewAI 1.14.7 reports anonymous usage to telemetry.crewai.com from every
process that imports it: its Telemetry object is built at import and, unless
one of three variables says otherwise, starts an exporter. No file in this
repository set any of them and neither did the deployment (checked on
2026-11-16), so the worker of every assessment reported the framework and
Python versions, the number of agents and tasks, and each agent's role name,
model name and tool names. Not the topic, a prompt, a report, a key or an
email address: those are sent only with ``share_crew``, which nothing here
sets. Even so, it was a recipient the privacy page does not list.

``academic_agent/__init__.py`` puts a watcher on the import system that sets
``CREWAI_DISABLE_TELEMETRY=true``, if the variable is not set, at the moment
CrewAI is about to be imported. Its docstring says why there and in that
form: two plainer places broke rules this suite holds (an import that must
read no environment; a file pre-registered experiments hold by hash).

These tests run a fresh interpreter each, because the question is what a new
process does: tests/conftest.py sets the variable for the test process
itself (tests/test_no_crewai_telemetry.py), which would hide the answer.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "academic_agent"
SWITCHES = ("CREWAI_DISABLE_TELEMETRY", "CREWAI_DISABLE_TRACKING", "OTEL_SDK_DISABLED")

REPORT = f"""
import json, os
from crewai.telemetry.telemetry import Telemetry
telemetry = Telemetry()
seen = {{"ready": telemetry.ready, "sends": telemetry._should_execute_telemetry()}}
seen.update((name, os.environ.get(name)) for name in {SWITCHES!r})
print(json.dumps(seen))
"""


def _loads_crewai(node: ast.AST) -> bool:
    if isinstance(node, ast.ImportFrom):
        names = [node.module or ""]
    elif isinstance(node, ast.Import):
        names = [alias.name for alias in node.names]
    else:
        return False
    return any(part == "crewai" for name in names for part in name.split("."))


def modules_that_load_crewai() -> list[str]:
    """Every module of the package with an import of CrewAI anywhere in it,
    at the top or inside a function, directly or through an instrumentor."""
    found = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if any(_loads_crewai(node) for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))):
            found.append(path.relative_to(PACKAGE).with_suffix("").as_posix().replace("/", "."))
    return found


LOADERS = modules_that_load_crewai()


def fresh(code: str, tmp_path, **environment) -> dict:
    """What a new interpreter prints, with none of the three switches inherited
    and no ``.env`` read: the deployment's own state, not this machine's."""
    env = {name: value for name, value in os.environ.items() if name not in SWITCHES}
    env.update({"PYTHON_DOTENV_DISABLED": "1", "PYTHONIOENCODING": "utf-8", **environment})
    done = subprocess.run([sys.executable, "-c", code], env=env, cwd=tmp_path, capture_output=True,
                          text=True, encoding="utf-8", timeout=180, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_crewai_alone_would_report(tmp_path):
    """The control: without this package, a new process is ready to send.
    If this ever stops holding, CrewAI changed and the tests below prove
    nothing by passing."""
    seen = fresh(REPORT, tmp_path)
    assert seen["ready"] is True and seen["sends"] is True
    assert seen["CREWAI_DISABLE_TELEMETRY"] is None


def test_the_modules_that_load_crewai_are_found():
    """The worker, the crew and the frozen evidence module among them; a
    scan that found nothing would make the next test pass over nothing."""
    assert {"pipeline_worker", "crew", "llm_config", "evidence", "observability.tracing"} <= set(LOADERS)
    assert "__init__" not in LOADERS, "The package's door must not load what it switches"
    assert len(LOADERS) >= 9


@pytest.mark.parametrize("name", LOADERS)
def test_a_process_that_starts_at_any_of_them_does_not_report(tmp_path, name):
    """Whichever comes first in a process: the worker of an assessment, the
    crew, the model configuration the API process loads for a plan preview,
    or a module nobody may edit."""
    seen = fresh(f"import academic_agent.{name}\n" + REPORT, tmp_path)
    assert seen["ready"] is False and seen["sends"] is False
    assert seen["CREWAI_DISABLE_TELEMETRY"] == "true"
    # Only CrewAI's switch. OTEL_SDK_DISABLED would also turn off the trace this
    # project sends to the operator's own collector; the third is CrewAI's older name.
    assert seen["OTEL_SDK_DISABLED"] is None and seen["CREWAI_DISABLE_TRACKING"] is None


def test_crewai_reached_through_another_package_is_covered_too(tmp_path):
    """The tracing module loads CrewAI by way of an instrumentor's import,
    and any submodule of CrewAI may be the first one asked for."""
    seen = fresh("import academic_agent\nimport crewai.utilities.constants\n" + REPORT, tmp_path)
    assert seen["ready"] is False and seen["CREWAI_DISABLE_TELEMETRY"] == "true"


@pytest.mark.parametrize("chosen", ["false", "true", "0"])
def test_an_operators_own_setting_is_kept(tmp_path, chosen):
    """Off is the default, not a rule: a value already in the environment is
    the operator's, and is neither replaced nor second-guessed."""
    seen = fresh("import academic_agent.pipeline_worker\n" + REPORT, tmp_path, CREWAI_DISABLE_TELEMETRY=chosen)
    assert seen["CREWAI_DISABLE_TELEMETRY"] == chosen
    assert seen["ready"] is (chosen != "true")


INERT = """
import json, os, sys
reads = []
original = type(os.environ).__getitem__
def watched(self, name):
    reads.append(name)
    return original(self, name)
type(os.environ).__getitem__ = watched
import academic_agent
package = list(reads)             # the package's own door: nothing at all
import academic_agent.report_evidence_snapshot
import email.mime.text            # an ordinary import after the watcher is in place
type(os.environ).__getitem__ = original
print(json.dumps({"package": package, "switches": [name for name in reads if "CREWAI" in name or "OTEL" in name],
                  "set": os.environ.get("CREWAI_DISABLE_TELEMETRY"),
                  "crewai": any(name == "crewai" or name.startswith("crewai.") for name in sys.modules),
                  "watchers": sum(getattr(finder, "__name__", "") == "_BeforeCrewAI" for finder in sys.meta_path)}))
"""


def test_the_package_itself_reads_nothing_and_sets_nothing(tmp_path):
    """Parts of the package run where the environment must not be read and
    CrewAI is never loaded (tests/test_saved_source_app.py). Importing the
    package, or a part that does not use CrewAI, leaves the environment as
    it was; the watcher is there, once, and other imports pass it by."""
    assert fresh(INERT, tmp_path) == {"package": [], "switches": [], "set": None, "crewai": False, "watchers": 1}


def test_the_watcher_finds_nothing_and_watches_one_name():
    """It must never answer for a module: that would be this package
    deciding what CrewAI is. And it must not fire for a neighbour's name."""
    code = """
import json, os, sys
import academic_agent
watcher = next(finder for finder in sys.meta_path if getattr(finder, "__name__", "") == "_BeforeCrewAI")
out = {}
for name in ("crewai_tools", "crewaix", "mycrewai", "openinference.instrumentation.crewai", "os", "academic_agent.crew"):
    out[name] = [watcher.find_spec(name), os.environ.get("CREWAI_DISABLE_TELEMETRY")]
for name in ("crewai", "crewai.telemetry.telemetry"):
    os.environ.pop("CREWAI_DISABLE_TELEMETRY", None)
    out[name] = [watcher.find_spec(name, None, None), os.environ.get("CREWAI_DISABLE_TELEMETRY")]
out["first"] = sys.meta_path[0] is watcher
print(json.dumps(out))
"""
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        seen = fresh(code, folder)
    for name in ("crewai_tools", "crewaix", "mycrewai", "openinference.instrumentation.crewai", "os", "academic_agent.crew"):
        assert seen[name] == [None, None], name
    for name in ("crewai", "crewai.telemetry.telemetry"):
        assert seen[name] == [None, "true"], name
    assert seen["first"] is True, "Ahead of the finders that would load CrewAI"


def test_the_operator_is_told():
    guide = (ROOT / "docs" / "operating-guide.md").read_text(encoding="utf-8")
    assert "### CrewAI's own usage reporting" in guide
    for said in ("`CREWAI_DISABLE_TELEMETRY=true`", "telemetry.crewai.com", "`CREWAI_DISABLE_TELEMETRY=false`",
                 "`OTEL_SDK_DISABLED`", "`share_crew`", "`src/academic_agent/__init__.py`"):
        assert said in guide, said
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "# CREWAI_DISABLE_TELEMETRY=false" in example and "telemetry.crewai.com" in example
    assert "src/academic_agent/__init__.py" in example
