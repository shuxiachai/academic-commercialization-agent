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
