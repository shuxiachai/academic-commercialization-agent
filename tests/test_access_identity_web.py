"""Selected credentials survive shared storage changes and stale auth responses."""

from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize("scenario,variant", [
    *[("cross_tab", kind) for kind in ["run", "pdf", "resume", "delete", "history"]],
    *[("rejected_request", kind) for kind in [
        "current", "candidate", "same_page", "aba", "other_tab", "other_logout"]],
    *[("logout", kind) for kind in [
        "normal", "other_tab", "other_logout", "read_denied", "remove_denied"]],
])
def test_document_identity_at_request_and_logout_seams(scenario, variant):
    """Shared localStorage and an old 401 used to overwrite or erase another payer."""
    node = shutil.which("node")
    assert node, "Node is required; missing execution is not a passing seam"
    script = Path(__file__).with_name("js") / "access_identity_contract.mjs"
    result = subprocess.run([node, str(script), scenario, variant], capture_output=True,
                            text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {scenario} {variant}" in result.stdout
