"""Static contracts for the executable GitHub Actions workflow."""

from __future__ import annotations

import re
from pathlib import Path


_WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "test.yml"
_ACTION_REF = re.compile(
    r"^\s*(?:-\s+)?uses:\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)@v(\d+)\s*$",
    re.MULTILINE,
)

# This is a reviewed runtime boundary, not a generic "latest is better" rule.
# Each minimum below is the first project-adopted major whose official
# action.yml declares Node 24.  Keeping the map explicit means a newly added
# JavaScript action cannot silently reintroduce GitHub's forced-Node-24 warning;
# its runtime must first be checked and recorded here.
_NODE24_MINIMUM_MAJOR = {
    "actions/checkout": 7,
    "astral-sh/setup-uv": 10,
    "docker/build-push-action": 7,
    "docker/setup-buildx-action": 4,
}


def test_ci_javascript_actions_use_reviewed_node24_majors() -> None:
    """Catch the exact old-major regression that polluted every CI job."""

    workflow = _WORKFLOW.read_text(encoding="utf-8")
    observed: dict[str, list[int]] = {}
    for action, major in _ACTION_REF.findall(workflow):
        observed.setdefault(action, []).append(int(major))

    # An unknown external action is not assumed safe.  The failure asks the
    # author to inspect its official action.yml instead of treating a green job
    # under GitHub's temporary compatibility shim as proof of compatibility.
    assert set(observed) == set(_NODE24_MINIMUM_MAJOR)
    for action, minimum_major in _NODE24_MINIMUM_MAJOR.items():
        assert all(major >= minimum_major for major in observed[action]), (
            f"{action} must use v{minimum_major}+ so every CI job runs on a "
            "reviewed Node 24 action runtime"
        )
