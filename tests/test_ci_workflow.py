"""Static contracts for the executable GitHub Actions workflow."""

from __future__ import annotations

import re
from pathlib import Path


_WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "test.yml"
_ACTION_REF = re.compile(
    r"^\s*(?:-\s+)?uses:\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@(v\d+(?:\.\d+\.\d+)?)\s*$",
    re.MULTILINE,
)

# This is a reviewed runtime boundary, not a generic "latest is better" rule.
# Each ref below exists upstream and its official action.yml declares Node 24.
# setup-uv is intentionally pinned to a full release because, unlike the other
# publishers, Astral does not expose a floating v10 ref.  Keeping exact reviewed
# refs here makes an unresolvable alias fail offline before GitHub tries to set
# up a job.
_REVIEWED_NODE24_REFS = {
    "actions/checkout": "v7",
    "actions/upload-artifact": "v6",
    "astral-sh/setup-uv": "v10.0.1",
    "docker/build-push-action": "v7",
    "docker/setup-buildx-action": "v4",
}


def test_ci_javascript_actions_use_reviewed_node24_refs() -> None:
    """Catch old runtimes and reviewed releases referenced through bad aliases."""

    workflow = _WORKFLOW.read_text(encoding="utf-8")
    observed: dict[str, list[str]] = {}
    for action, ref in _ACTION_REF.findall(workflow):
        observed.setdefault(action, []).append(ref)

    # An unknown external action is not assumed safe.  The failure asks the
    # author to inspect its official action.yml instead of treating a green job
    # under GitHub's temporary compatibility shim as proof of compatibility.
    assert set(observed) == set(_REVIEWED_NODE24_REFS)
    for action, reviewed_ref in _REVIEWED_NODE24_REFS.items():
        assert all(ref == reviewed_ref for ref in observed[action]), (
            f"{action} must use reviewed ref {reviewed_ref} so every CI job "
            "runs on a resolvable Node 24 action runtime"
        )


def test_ci_fails_instead_of_silently_skipping_node_backed_tests() -> None:
    """The local skip is ergonomic; the four CI test jobs require the runtime."""

    workflow = _WORKFLOW.read_text(encoding="utf-8")
    preflight_name = "- name: Require Node for web contract tests"
    preflight_command = "run: node --version"
    pytest_command = "pytest tests/ -v --tb=short"

    assert workflow.count(preflight_name) == 2
    assert workflow.count(preflight_command) == 2
    assert workflow.count(pytest_command) == 1
    assert workflow.index(preflight_name) < workflow.index(preflight_command)
    assert workflow.index(preflight_command) < workflow.index(pytest_command), (
        "Node must be required inside the test job before pytest can convert "
        "missing JavaScript coverage into unittest skips"
    )


def test_ci_enforces_the_measured_coverage_floor_in_one_canonical_job() -> None:
    """The resume's coverage number must stay executable, not aspirational.

    The gate is intentionally single-platform. Repeating it across the matrix
    would let defensive OS branches create four subtly different project
    metrics, while adding no new functional coverage beyond the matrix itself.
    """

    workflow = _WORKFLOW.read_text(encoding="utf-8")
    coverage_start = workflow.index("  coverage:")
    coverage_end = workflow.index("  browser-smoke:")
    coverage_job = workflow[coverage_start:coverage_end]

    assert workflow.count("--cov-fail-under=85") == 1
    assert "--cov=src/academic_agent" in coverage_job
    assert "--cov=api" in coverage_job
    assert "--cov=ui" in coverage_job
    assert "--cov-report=term-missing" in coverage_job
    assert coverage_job.index("run: node --version") < coverage_job.index(
        "--cov-fail-under=85"
    )
