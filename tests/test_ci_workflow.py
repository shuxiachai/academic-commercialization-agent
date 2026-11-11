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
# Serial until the timing-sensitive concurrency tests are parallel-safe.
_FULL_RUN = f"uv run --python {_PYTHON} pytest tests/ -v --tb=short --durations=40"
# Non-coverage PR cells skip tests of closed experiments; the coverage cell
# and the weekly full-suite workflow run everything.
_PLAIN_RUN = f'uv run --python {_PYTHON} pytest tests/ -m "not experiment" -v --tb=short --durations=40'
# Each cell is split by test file over this many runners (tests/conftest.py,
# ACA_TEST_SHARD); a part still runs serially on a runner of its own. The
# number appears in the matrix, in the variable and in the floor's count of
# parts, and the contract below holds the three together.
_SHARDS = 3
_SHARD_ENV = {"ACA_TEST_SHARD": f"${{{{ matrix.shard }}}}/{_SHARDS}"}
_COVERAGE_DATA = ".coverage.${{ matrix.shard }}"
# One part covers a third of the suite, so the floor is not applied in the
# cell: each part records its data and the coverage job applies the floor to
# the combined total. Scope and floor are unchanged.
_COVERAGE_RUN = f"{_FULL_RUN} --cov=src/academic_agent --cov=api --cov=ui --cov-report="
_COVERAGE_UPLOAD = {
    "name": "coverage-data-${{ matrix.shard }}", "path": _COVERAGE_DATA,
    "include-hidden-files": True, "if-no-files-found": "error", "retention-days": 1,
}
_GATE = 'test "$MATRIX_RESULT" = success'
_GATE_ENV = {"MATRIX_RESULT": "${{ needs.test.result }}"}
_FLOOR_SYNC = "uv sync --python 3.12"
_FLOOR_PARTS = f'test "$(ls .coverage.* | wc -l)" = {_SHARDS}'
_FLOOR_COMBINE = "uv run --python 3.12 coverage combine"
_FLOOR_REPORT = "uv run --python 3.12 coverage report --show-missing --fail-under=85"
_FLOOR_DOWNLOAD = {"pattern": "coverage-data-*", "merge-multiple": True}
_WEEKLY = _WORKFLOW.with_name("full-suite.yml")
# The coverage cell measures with sys.monitoring; the floor and scope above
# are unchanged, only the measurement overhead is.
_COVERAGE_ENV = {"COVERAGE_CORE": "sysmon", "COVERAGE_FILE": _COVERAGE_DATA}
_CELLS = set(product(("ubuntu-latest", "windows-latest"), ("3.11", "3.12")))
_CANONICAL = {("ubuntu-latest", "3.12")}
# These are the only admitted conditional forms, not an Actions interpreter.
_CONDITION_CELLS = {_PLAIN_IF: _CELLS - _CANONICAL, _COVERAGE_IF: _CANONICAL}

# Each reviewed upstream action.yml declares Node 24. Astral does not expose
# a floating v10 alias, so its full reviewed release remains intentional.
# Each action is pinned to the commit its reviewed tag pointed at when it was
# reviewed (the tag is kept as a comment in the workflow). A tag can be moved
# by whoever controls the action's repository; a commit cannot. Dependabot
# proposes the next commit when a new release appears.
_REVIEWED_NODE24_REFS = {
    "actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",            # v7
    "actions/download-artifact": "9000827ccba6bdab643e8b6fd33ac0654aef8333",   # v8.0.2
    "actions/upload-artifact": "cf430e030ddbb5b0abf93d22962f4752f3646cd9",     # v7.0.2
    "astral-sh/setup-uv": "68559e99cc807c1eb7e9238fd43a15bba460eec2",         # v10.3.3
    "docker/build-push-action": "c3c9e263c25d99ce0380d002d59b67737d91b0dc",   # v7
    "docker/setup-buildx-action": "f87e5991a6d7451dcb8d9637bfbc97413f497069", # v4
}
# The branch ruleset requires eight names: the four cell names, lint, the
# coverage floor, the browser smoke and the docker build. The split parts
# carry a name of their own; the `cells` job keeps the four the ruleset knows.
_CHECK_NAMES = {
    "test": f"pytest (${{{{ matrix.os }}}}, py${{{{ matrix.python-version }}}}, part ${{{{ matrix.shard }}}} of {_SHARDS})",
    "cells": "pytest (${{ matrix.os }}, py${{ matrix.python-version }})",
    "lint": "lint",
    "coverage": "coverage floor (Ubuntu, py3.12)",
    "browser-smoke": "browser smoke (Chromium, zero-provider)",
    "docker": "docker build",
}


def _workflow():
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))


def _jobs():
    return _workflow()["jobs"]


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


def _uses_index(steps, action):
    return _one_index([
        index for index, step in enumerate(steps)
        if step.get("uses") == f"{action}@{_REVIEWED_NODE24_REFS[action]}"
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
    assert set(matrix) == {"os", "python-version", "shard"}
    assert sorted(matrix["os"]) == ["ubuntu-latest", "windows-latest"]
    assert sorted(matrix["python-version"]) == ["3.11", "3.12"]
    # Every part from 1 to the number the variable divides by: a part left
    # out of the matrix is a third of the suite that no runner ever runs.
    assert matrix["shard"] == list(range(1, _SHARDS + 1))
    assert job.get("env") == _SHARD_ENV, "Every part must be told which part of how many it is"

    steps = job["steps"]
    checkout = _uses_index(steps, "actions/checkout")
    setup = _uses_index(steps, "astral-sh/setup-uv")
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
            assert step.get("env") == (_COVERAGE_ENV if command == _tokens(_COVERAGE_RUN) else None)
            assert step.get("continue-on-error", False) is False
            condition = _condition(step.get("if"))
            assert condition in _CONDITION_CELLS
            assert node < index, "Node preflight must precede every pytest path"
            executions.append((condition, command, index))

    for cell in product(matrix["os"], matrix["python-version"]):
        selected = [
            command for condition, command, _index in executions
            if cell in _CONDITION_CELLS[condition]
        ]
        expected = _COVERAGE_RUN if cell in _CANONICAL else _PLAIN_RUN
        assert selected == [_tokens(expected)], (
            f"{cell} must execute its part of the verbose suite exactly once; "
            "only Ubuntu 3.12 owns the unchanged coverage scope"
        )

    # The canonical cell's data must leave the runner, or the floor below
    # would be applied to nothing. A dotfile needs include-hidden-files.
    upload = _uses_index(steps, "actions/upload-artifact")
    coverage_run = _one_index([index for _c, command, index in executions if command == _tokens(_COVERAGE_RUN)])
    assert coverage_run < upload
    assert _condition(steps[upload].get("if")) == _COVERAGE_IF
    assert steps[upload].get("continue-on-error", False) is False
    assert steps[upload]["with"] == _COVERAGE_UPLOAD


def _assert_gate_step(step):
    _unconditional(step)
    assert "uses" not in step
    assert step["shell"] == "bash"
    assert step["env"] == _GATE_ENV
    # Quotes are executable semantics here: single quotes would compare the
    # literal variable name and fail even when the matrix succeeds.
    commands = [line.strip() for line in step["run"].splitlines()
                if line.strip() and not line.lstrip().startswith("#")]
    assert commands == [_GATE]


def _assert_cells_gate(jobs):
    """The four names the ruleset requires are green only when every part passed."""
    job = jobs["cells"]
    assert job["runs-on"] == "ubuntu-latest"
    assert job["needs"] in ("test", ["test"])
    assert _condition(job["if"]) == "always()"
    assert job.get("continue-on-error", False) is False
    matrix = job["strategy"]["matrix"]
    assert set(matrix) == {"os", "python-version"}
    assert set(product(matrix["os"], matrix["python-version"])) == _CELLS
    assert len(job["steps"]) == 1, "The compatibility gate must not rerun tests"
    _assert_gate_step(job["steps"][0])


def _assert_coverage_floor(jobs):
    job = jobs["coverage"]
    assert job["runs-on"] == "ubuntu-latest"
    assert job["needs"] in ("test", ["test"])
    assert _condition(job["if"]) == "always()"
    assert job.get("continue-on-error", False) is False
    assert "strategy" not in job
    steps = job["steps"]
    # First, so a failed or skipped matrix stops the job before anything else.
    _assert_gate_step(steps[0])
    checkout = _uses_index(steps, "actions/checkout")
    setup = _uses_index(steps, "astral-sh/setup-uv")
    assert steps[setup]["with"]["python-version"] == "3.12"
    sync = _run_index(steps, _FLOOR_SYNC)
    download = _uses_index(steps, "actions/download-artifact")
    assert steps[download]["with"] == _FLOOR_DOWNLOAD
    parts = _run_index(steps, _FLOOR_PARTS)
    assert steps[parts]["shell"] == "bash"
    combine = _run_index(steps, _FLOOR_COMBINE)
    report = _run_index(steps, _FLOOR_REPORT)
    order = [0, checkout, setup, sync, download, parts, combine, report]
    assert order == sorted(order) and len(set(order)) == len(order)
    assert len(steps) == len(order), "Nothing else runs in the floor job"
    for index in order:
        _unconditional(steps[index])


def _assert_browser(jobs):
    job = jobs["browser-smoke"]
    _unconditional(job)
    commands = (
        "uv sync --python 3.12 --group e2e",
        "uv run --python 3.12 --group e2e playwright install --with-deps chromium",
        "uv run --python 3.12 --group e2e python -m e2e.browser_smoke",
        "uv run --python 3.12 --group e2e python -m e2e.composer_smoke",
        "uv run --python 3.12 --group e2e python -m e2e.keyboard_smoke",
    )
    indices = [_run_index(job["steps"], command) for command in commands]
    assert indices == sorted(indices)
    for index in indices:
        _unconditional(job["steps"][index])


def _assert_all(jobs):
    _assert_actions(jobs)
    _assert_test_execution(jobs)
    _assert_cells_gate(jobs)
    _assert_coverage_floor(jobs)
    _assert_browser(jobs)


def test_ci_executable_contracts():
    """Reject skipped/duplicate suites, fake commands, and green skipped gates."""
    jobs = _jobs()
    assert {key: job["name"] for key, job in jobs.items()} == _CHECK_NAMES
    _assert_all(jobs)


def test_a_newer_push_to_a_pull_request_replaces_its_older_run_and_main_is_never_cancelled():
    concurrency = _workflow()["concurrency"]
    assert " ".join(concurrency["group"].split()) == "tests-${{ github.event.pull_request.number || github.sha }}"
    assert _condition(concurrency["cancel-in-progress"]) == "github.event_name == 'pull_request'"


@pytest.mark.parametrize(("command", "update"), [
    ("node --version", {"run": "# node --version"}),
    ("node --version", {"run": "echo node --version"}),
    ("node --version", {"if": False}),
    ("node --version", {"continue-on-error": True}),
    (_PLAIN_RUN, {"if": _COVERAGE_IF}),
    (_COVERAGE_RUN, {"if": _PLAIN_IF}),
    (_COVERAGE_RUN, {"if": "false"}),
    (_COVERAGE_RUN, {"run": "# " + _COVERAGE_RUN}),
    (_COVERAGE_RUN, {"run": _COVERAGE_RUN.replace(" --cov=ui", "")}),
    (_PLAIN_RUN, {"run": _PLAIN_RUN.replace(" --durations=40", "")}),
    (_COVERAGE_RUN, {"run": _COVERAGE_RUN.replace(" --durations=40", "")}),
    (_PLAIN_RUN, {"run": _PLAIN_RUN.replace("--durations=40", "--durations=10")}),
    (_COVERAGE_RUN, {"run": _COVERAGE_RUN.replace("--durations=40", "--durations=10")}),
    (_PLAIN_RUN, {"run": _PLAIN_RUN + " || true"}),
    (_PLAIN_RUN, {"run": _PLAIN_RUN + " -k smoke"}),
    (_COVERAGE_RUN, {"continue-on-error": True}),
    (_COVERAGE_RUN, {"env": {"COVERAGE_CORE": "ctrace", "COVERAGE_FILE": _COVERAGE_DATA}}),
    # One data file for every part would have each upload overwrite the last.
    (_COVERAGE_RUN, {"env": {"COVERAGE_CORE": "sysmon"}}),
    (_COVERAGE_RUN, {"env": {"COVERAGE_CORE": "sysmon", "COVERAGE_FILE": ".coverage"}}),
    (_PLAIN_RUN, {"env": _COVERAGE_ENV}),
    # The coverage cell is the only per-PR run of the experiment tests.
    (_COVERAGE_RUN, {"run": _COVERAGE_RUN.replace("tests/ ", 'tests/ -m "not experiment" ')}),
    (_PLAIN_RUN, {"run": _PLAIN_RUN.replace("not experiment", "not experiment and not slow")}),
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
    "missing-part", "extra-part", "part-not-told", "part-of-another-number",
    "data-not-kept", "data-hidden", "data-optional", "data-kept-before-run", "data-kept-everywhere",
])
def test_execution_contract_rejects_broken_topology(defect):
    """Step order and expanded matrix execution matter, not textual counts."""
    jobs = _jobs()
    job = jobs["test"]
    steps = job["steps"]
    upload = _uses_index(steps, "actions/upload-artifact")
    if defect == "late-node":
        steps.append(steps.pop(_run_index(steps, "node --version")))
    elif defect == "duplicate-suite":
        steps.append(dict(steps[_run_index(steps, _PLAIN_RUN)]))
    elif defect == "extra-suite-job":
        jobs["extra"] = {"steps": [{"run": _PLAIN_RUN}]}
    elif defect == "missing-cell":
        job["strategy"]["matrix"]["os"] = ["ubuntu-latest"]
    elif defect == "ignored-job":
        job["continue-on-error"] = True
    elif defect == "missing-part":
        # Two runners told they are parts of three: a third of the tests never run.
        job["strategy"]["matrix"]["shard"] = [1, 2]
    elif defect == "extra-part":
        job["strategy"]["matrix"]["shard"] = [1, 2, 3, 4]
    elif defect == "part-not-told":
        # Without the variable every runner runs the whole suite: correct, and three times the wait.
        del job["env"]
    elif defect == "part-of-another-number":
        job["env"] = {"ACA_TEST_SHARD": "${{ matrix.shard }}/2"}
    elif defect == "data-not-kept":
        steps.pop(upload)
    elif defect == "data-hidden":
        steps[upload]["with"]["include-hidden-files"] = False
    elif defect == "data-optional":
        steps[upload]["with"]["if-no-files-found"] = "warn"
    elif defect == "data-kept-before-run":
        steps.insert(0, steps.pop(upload))
    else:
        steps[upload].pop("if")
    with pytest.raises(AssertionError):
        _assert_test_execution(jobs)


_FALSE_GATES = [
    ("job", {"needs": "lint"}),
    ("job", {"if": "success()"}),
    ("job", {"continue-on-error": True}),
    ("step", {"if": "success()"}),
    ("step", {"env": {"MATRIX_RESULT": "success"}}),
    ("step", {"run": 'echo test "$MATRIX_RESULT" = success'}),
    ("step", {"run": "test '$MATRIX_RESULT' = success"}),
    ("step", {"run": 'test "$MATRIX_RESULT" = success || true'}),
]


@pytest.mark.parametrize(("target", "update"), _FALSE_GATES)
def test_cells_gate_rejects_false_success(target, update):
    """A skipped, hardcoded, or failure-swallowing compatibility gate is unsafe."""
    jobs = _jobs()
    job = jobs["cells"]
    (job if target == "job" else job["steps"][0]).update(update)
    with pytest.raises(AssertionError):
        _assert_cells_gate(jobs)


def test_cells_gate_names_every_cell_the_ruleset_requires():
    jobs = _jobs()
    jobs["cells"]["strategy"]["matrix"]["os"] = ["ubuntu-latest"]
    with pytest.raises(AssertionError):
        _assert_cells_gate(jobs)


@pytest.mark.parametrize(("target", "update"), _FALSE_GATES)
def test_coverage_floor_rejects_false_success(target, update):
    jobs = _jobs()
    job = jobs["coverage"]
    (job if target == "job" else job["steps"][0]).update(update)
    with pytest.raises(AssertionError):
        _assert_coverage_floor(jobs)


@pytest.mark.parametrize("defect", [
    "lower-floor", "no-floor", "combine-skipped", "parts-not-counted", "two-parts-enough",
    "other-artifacts", "parts-in-folders", "download-optional", "report-optional", "gate-last", "tests-here",
])
def test_coverage_floor_rejects_a_floor_that_measures_less(defect):
    """The floor is applied to the total of every part, or it is not the floor."""
    jobs = _jobs()
    steps = jobs["coverage"]["steps"]
    report = _run_index(steps, _FLOOR_REPORT)
    combine = _run_index(steps, _FLOOR_COMBINE)
    parts = _run_index(steps, _FLOOR_PARTS)
    download = _uses_index(steps, "actions/download-artifact")
    if defect == "lower-floor":
        steps[report]["run"] = _FLOOR_REPORT.replace("=85", "=84")
    elif defect == "no-floor":
        steps[report]["run"] = _FLOOR_REPORT.replace(" --fail-under=85", "")
    elif defect == "combine-skipped":
        steps[combine]["run"] = "# " + _FLOOR_COMBINE
    elif defect == "parts-not-counted":
        steps.pop(parts)
    elif defect == "two-parts-enough":
        steps[parts]["run"] = _FLOOR_PARTS.replace(f"= {_SHARDS}", "= 2")
    elif defect == "other-artifacts":
        steps[download]["with"]["pattern"] = "*"
    elif defect == "parts-in-folders":
        # Unmerged, each part lands in a folder of its own and combine finds none.
        steps[download]["with"]["merge-multiple"] = False
    elif defect == "download-optional":
        steps[download]["continue-on-error"] = True
    elif defect == "report-optional":
        steps[report]["if"] = "success()"
    elif defect == "gate-last":
        steps.append(steps.pop(0))
    else:
        steps.append({"run": _PLAIN_RUN})
    with pytest.raises(AssertionError):
        _assert_all(jobs)


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


@pytest.mark.parametrize("ref", ["actions/checkout@v7", "astral-sh/setup-uv@v10.3.3", "actions/download-artifact@v8"])
def test_action_contract_rejects_unreviewed_refs(ref):
    """Inspect actual uses nodes even if another valid ref still exists elsewhere."""
    jobs = _jobs()
    jobs["test"]["steps"].append({"uses": ref})
    with pytest.raises(AssertionError):
        _assert_actions(jobs)


def _assert_weekly(workflow):
    triggers = workflow.get("on", workflow.get(True))  # YAML 1.1 reads a bare `on` as True
    assert triggers["schedule"] and "workflow_dispatch" in triggers
    (job,) = workflow["jobs"].values()
    _unconditional(job)
    assert job["runs-on"] == "${{ matrix.os }}"
    assert job["strategy"]["fail-fast"] is False
    matrix = job["strategy"]["matrix"]
    # Whole, on every cell: the weekly run is not split and is told of no part.
    assert set(matrix) == {"os", "python-version"}
    assert "ACA_TEST_SHARD" not in (job.get("env") or {})
    assert sorted(matrix["os"]) == ["ubuntu-latest", "windows-latest"]
    assert sorted(matrix["python-version"]) == ["3.11", "3.12"]
    steps = job["steps"]
    assert {step["uses"] for step in steps if "uses" in step} == {
        f"{action}@{_REVIEWED_NODE24_REFS[action]}" for action in ("actions/checkout", "astral-sh/setup-uv")
    }
    sync = _run_index(steps, f"uv sync --python {_PYTHON}")
    node = _run_index(steps, "node --version")
    suite = _run_index(steps, _FULL_RUN)
    assert sync < node < suite
    for index in (sync, node, suite):
        _unconditional(steps[index])
    assert sum("pytest" in _tokens(step.get("run", "")) for step in steps) == 1


def test_weekly_workflow_runs_the_complete_suite_on_every_cell():
    """The only place experiment tests run on Windows and Python 3.11."""
    _assert_weekly(yaml.safe_load(_WEEKLY.read_text(encoding="utf-8")))


@pytest.mark.parametrize("defect", ["filtered", "no-schedule", "one-cell", "skipped", "one-part"])
def test_weekly_contract_rejects_a_partial_suite(defect):
    workflow = yaml.safe_load(_WEEKLY.read_text(encoding="utf-8"))
    triggers = workflow.get("on", workflow.get(True))
    (job,) = workflow["jobs"].values()
    suite = _run_index(job["steps"], _FULL_RUN)
    if defect == "filtered":
        job["steps"][suite]["run"] = _PLAIN_RUN
    elif defect == "no-schedule":
        triggers.pop("schedule")
    elif defect == "one-cell":
        job["strategy"]["matrix"]["os"] = ["ubuntu-latest"]
    elif defect == "one-part":
        job["env"] = {"ACA_TEST_SHARD": "1/3"}
    else:
        job["steps"][suite]["if"] = "false"
    with pytest.raises((AssertionError, KeyError)):
        _assert_weekly(workflow)


def test_contracts_ignore_step_labels_comments_and_job_order():
    """Harmless presentation edits must not require rewriting CI contracts."""
    jobs = dict(reversed(list(_jobs().items())))
    for job in jobs.values():
        for step in job["steps"]:
            step["name"] = "A renamed step"
            if "run" in step:
                step["run"] = "# A harmless shell comment\n" + step["run"]
    _assert_all(jobs)
