"""Request-level regressions for the paid composer, with no network or keys."""

from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize("scenario", [
    "pending_submit", "rejected_submit", "existing_topic_pdf", "empty_topic_pdf",
    "missing_suggestion_pdf", "serialized_pdf", "stale_pdf_response", "failed_pdf",
    "upload_during_submit", "classified_errors",
    "accepted_history_failure", "resume_rerender", "lost_acknowledgement", "malformed_history",
])
def test_composer_delivers_one_intended_operation(scenario):
    """Input events and delayed extraction cannot duplicate or change paid intent."""
    node = shutil.which("node")
    assert node is not None, "Node is required for the shipped client contract."
    script = Path(__file__).with_name("js") / "composer_contract.mjs"
    result = subprocess.run(
        [node, str(script), scenario], capture_output=True, text=True,
        encoding="utf-8", timeout=30, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {scenario}" in result.stdout
