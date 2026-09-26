"""Bounded structural contracts for the executable GitHub Actions workflow."""

from __future__ import annotations

import shlex
from itertools import product
from pathlib import Path

import pytest
import yaml


_WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "test.yml"
_PYTHON = "${{ matrix.python-version }}"
_PLAIN_IF = "matrix.os != 'ubuntu-latest' || matrix.python-version != '3.12'"
_COVERAGE_IF = "matrix.os == 'ubuntu-latest' && matrix.python-version == '3.12'"
_PLAIN_RUN = f"uv run --python {_PYTHON} pytest tests/ -v --tb=short --durations=40"
_COVERAGE_RUN = (
    f"{_PLAIN_RUN} --cov=src/academic_agent --cov=api --cov=ui "
    "--cov-report=term-missing --cov-fail-under=85"
)
_CELLS = set(product(("ubuntu-latest", "windows-latest"), ("3.11", "3.12")))
_CANONICAL = {("ubuntu-latest", "3.12")}
# These are the only admitted conditional forms, not an Actions interpreter.
_CONDITION_CELLS = {_PLAIN_IF: _CELLS - _CANONICAL, _COVERAGE_IF: _CANONICAL}

# Each reviewed upstream action.yml declares Node 24. Astral does not expose
# a floating v10 alias, so its full reviewed release remains intentional.
_REVIEWED_NODE24_REFS = {
    "actions/checkout": "v7",
    "actions/upload-artifact": "v6",
    "astral-sh/setup-uv": "v10.0.1",
    "docker/build-push-action": "v7",
    "docker/setup-buildx-action": "v4",
}
_CHECK_NAMES = {
    "test": "pytest (${{ matrix.os }}, py${{ matrix.python-version }})",
    "lint": "lint",
    "coverage": "coverage floor (Ubuntu, py3.12)",
    "browser-smoke": "browser smoke (Chromium, zero-provider)",
    "docker": "docker build",
}


def _jobs():
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def _tokens(command):
    # Tokenize only: no shell evaluation. Whole-command comparisons reject
    # echo, comments in place of commands, filters, and failure-swallowing tails.
    return shlex.split(command.replace(_PYTHON, "MATRIX_PYTHON"), comments=True)


def _condition(value):
    assert isinstance(value, str), "CI conditions must be explicit expressions"
    value = value.strip()
    if value.startswith("${{") and value.endswith("}}"):
        value = value[3:-2]
    return " ".join(value.split())


def _unconditional(node):
    assert "if" not in node, "Required CI work must not be conditional"
    assert node.get("continue-on-error", False) is False


def _one_index(indices):
    assert len(indices) == 1, "Expected exactly one executable step"
    return indices[0]


def _run_index(steps, command):
    return _one_index([
        index for index, step in enumerate(steps)
        if _tokens(step.get("run", "")) == _tokens(command)
    ])


def _assert_actions(jobs):
    observed = [
        step["uses"] for job in jobs.values() for step in job["steps"]
        if "uses" in step
    ]
    assert set(observed) == {
        f"{action}@{ref}" for action, ref in _REVIEWED_NODE24_REFS.items()
    }, "Every executable action must use its exact reviewed Node 24 ref"


def _assert_test_execution(jobs):
    job = jobs["test"]
    _unconditional(job)
    assert job["runs-on"] == "${{ matrix.os }}"
    assert job["strategy"]["fail-fast"] is False
    matrix = job["strategy"]["matrix"]
    assert set(matrix) == {"os", "python-version"}
    assert sorted(matrix["os"]) == ["ubuntu-latest", "windows-latest"]
    assert sorted(matrix["python-version"]) == ["3.11", "3.12"]

    steps = job["steps"]
    checkout = _one_index([
        i for i, step in enumerate(steps) if step.get("uses") == "actions/checkout@v7"
    ])
    setup = _one_index([
        i for i, step in enumerate(steps)
        if step.get("uses") == "astral-sh/setup-uv@v10.0.1"
    ])
    assert steps[setup]["with"]["python-version"] == _PYTHON
    sync = _run_index(steps, f"uv sync --python {_PYTHON}")
    node = _run_index(steps, "node --version")
    assert checkout < setup < sync < node
    for index in (checkout, setup, sync, node):
        _unconditional(steps[index])

    executions = []
    for owner, candidate in jobs.items():
        for index, step in enumerate(candidate["steps"]):
            command = _tokens(step.get("run", ""))
            if "pytest" not in command:
                continue
            assert owner == "test", "No extra full-suite job alongside the matrix"
            assert command in (_tokens(_PLAIN_RUN), _tokens(_COVERAGE_RUN))
            assert step.get("continue-on-error", False) is False
            condition = _condition(step.get("if"))
            assert condition in _CONDITION_CELLS
            assert node < index, "Node preflight must precede every pytest path"
            executions.append((condition, command))

    for cell in product(matrix["os"], matrix["python-version"]):
        selected = [
            command for condition, command in executions
            if cell in _CONDITION_CELLS[condition]
        ]
        expected = _COVERAGE_RUN if cell in _CANONICAL else _PLAIN_RUN
        assert selected == [_tokens(expected)], (
            f"{cell} must execute the full verbose suite exactly once; "
            "only Ubuntu 3.12 owns the unchanged coverage scope and 85% floor"
        )


def _assert_coverage_gate(jobs):
    job = jobs["coverage"]
    assert job["runs-on"] == "ubuntu-latest"
    assert job["needs"] in ("test", ["test"])
    assert _condition(job["if"]) == "always()"
    assert job.get("continue-on-error", False) is False
    assert "strategy" not in job
    assert len(job["steps"]) == 1, "The compatibility gate must not rerun tests"
    step = job["steps"][0]
    _unconditional(step)
    assert "uses" not in step
    assert step["shell"] == "bash"
    assert step["env"] == {"MATRIX_RESULT": "${{ needs.test.result }}"}
    # Quotes are executable semantics here: single quotes would compare the
    # literal variable name and fail even when the matrix succeeds.
    commands = [line.strip() for line in step["run"].splitlines()
                if line.strip() and not line.lstrip().startswith("#")]
    assert commands == ['test "$MATRIX_RESULT" = success']


def _assert_browser(jobs):
    job = jobs["browser-smoke"]
    _unconditional(job)
    commands = (
        "uv sync --python 3.12 --group e2e",
        "uv run --python 3.12 --group e2e playwright install --with-deps chromium",
        "uv run --python 3.12 --group e2e python -m e2e.browser_smoke",
        "uv run --python 3.12 --group e2e python -m e2e.composer_smoke",
    )
    indices = [_run_index(job["steps"], command) for command in commands]
    assert indices == sorted(indices)
    for index in indices:
        _unconditional(job["steps"][index])


def test_ci_executable_contracts():
    """Reject skipped/duplicate suites, fake commands, and green skipped gates."""
    jobs = _jobs()
    assert {key: job["name"] for key, job in jobs.items()} == _CHECK_NAMES
    _assert_actions(jobs)
    _assert_test_execution(jobs)
    _assert_coverage_gate(jobs)
    _assert_browser(jobs)


@pytest.mark.parametrize(("command", "update"), [
    ("node --version", {"run": "# node --version"}),
    ("node --version", {"run": "echo node --version"}),
    ("node --version", {"if": False}),
    ("node --version", {"continue-on-error": True}),
    (_PLAIN_RUN, {"if": _COVERAGE_IF}),
    (_COVERAGE_RUN, {"if": _PLAIN_IF}),
    (_COVERAGE_RUN, {"if": "false"}),
    (_COVERAGE_RUN, {"run": "# " + _COVERAGE_RUN}),
    (_COVERAGE_RUN, {"run": _COVERAGE_RUN.replace("=85", "=84")}),
    (_COVERAGE_RUN, {"run": _COVERAGE_RUN.replace(" --cov=ui", "")}),
    (_PLAIN_RUN, {"run": _PLAIN_RUN.replace(" --durations=40", "")}),
    (_COVERAGE_RUN, {"run": _COVERAGE_RUN.replace(" --durations=40", "")}),
    (_PLAIN_RUN, {"run": _PLAIN_RUN.replace("--durations=40", "--durations=10")}),
    (_COVERAGE_RUN, {"run": _COVERAGE_RUN.replace("--durations=40", "--durations=10")}),
    (_PLAIN_RUN, {"run": _PLAIN_RUN + " || true"}),
    (_PLAIN_RUN, {"run": _PLAIN_RUN + " -k smoke"}),
    (_COVERAGE_RUN, {"continue-on-error": True}),
])
def test_execution_contract_rejects_weakened_steps(command, update):
    """Reject execution/timing bypasses in memory, not by corrupting CI on disk."""
    jobs = _jobs()
    steps = jobs["test"]["steps"]
    steps[_run_index(steps, command)].update(update)
    with pytest.raises(AssertionError):
        _assert_test_execution(jobs)


@pytest.mark.parametrize("defect", [
    "late-node", "duplicate-suite", "extra-suite-job", "missing-cell", "ignored-job",
])
def test_execution_contract_rejects_broken_topology(defect):
    """Step order and expanded matrix execution matter, not textual counts."""
    jobs = _jobs()
    job = jobs["test"]
    steps = job["steps"]
    if defect == "late-node":
        steps.append(steps.pop(_run_index(steps, "node --version")))
    elif defect == "duplicate-suite":
        steps.append(dict(steps[_run_index(steps, _PLAIN_RUN)]))
    elif defect == "extra-suite-job":
        jobs["extra"] = {"steps": [{"run": _PLAIN_RUN}]}
    elif defect == "missing-cell":
        job["strategy"]["matrix"]["os"] = ["ubuntu-latest"]
    else:
        job["continue-on-error"] = True
    with pytest.raises(AssertionError):
        _assert_test_execution(jobs)


@pytest.mark.parametrize(("target", "update"), [
    ("job", {"needs": "lint"}),
    ("job", {"if": "success()"}),
    ("job", {"continue-on-error": True}),
    ("step", {"if": "success()"}),
    ("step", {"env": {"MATRIX_RESULT": "success"}}),
    ("step", {"run": 'echo test "$MATRIX_RESULT" = success'}),
    ("step", {"run": "test '$MATRIX_RESULT' = success"}),
    ("step", {"run": 'test "$MATRIX_RESULT" = success || true'}),
])
def test_coverage_gate_rejects_false_success(target, update):
    """A skipped, hardcoded, or failure-swallowing compatibility gate is unsafe."""
    jobs = _jobs()
    job = jobs["coverage"]
    (job if target == "job" else job["steps"][0]).update(update)
    with pytest.raises(AssertionError):
        _assert_coverage_gate(jobs)


@pytest.mark.parametrize("update", [
    {"run": "# python -m e2e.composer_smoke"},
    {"run": "echo python -m e2e.composer_smoke"},
    {"if": False},
])
def test_browser_contract_rejects_nonexecuting_journey(update):
    """A composer name or comment is not execution alongside the read-only path."""
    jobs = _jobs()
    steps = jobs["browser-smoke"]["steps"]
    command = "uv run --python 3.12 --group e2e python -m e2e.composer_smoke"
    steps[_run_index(steps, command)].update(update)
    with pytest.raises(AssertionError):
        _assert_browser(jobs)


@pytest.mark.parametrize("ref", ["actions/checkout@v6", "astral-sh/setup-uv@v10"])
def test_action_contract_rejects_unreviewed_refs(ref):
    """Inspect actual uses nodes even if another valid ref still exists elsewhere."""
    jobs = _jobs()
    jobs["test"]["steps"].append({"uses": ref})
    with pytest.raises(AssertionError):
        _assert_actions(jobs)


def test_contracts_ignore_step_labels_comments_and_job_order():
    """Harmless presentation edits must not require rewriting CI contracts."""
    jobs = dict(reversed(list(_jobs().items())))
    for job in jobs.values():
        for step in job["steps"]:
            step["name"] = "A renamed step"
            if "run" in step:
                step["run"] = "# A harmless shell comment\n" + step["run"]
    _assert_actions(jobs)
    _assert_test_execution(jobs)
    _assert_coverage_gate(jobs)
    _assert_browser(jobs)
