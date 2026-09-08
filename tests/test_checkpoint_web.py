"""Browser seams for checkpoint recovery.

The backend tests prove reuse. These assertions prove the values and the new
child id reach the shipped client, which is where earlier features disappeared
despite being computed and stored correctly.
"""

from pathlib import Path
import shutil
import subprocess


_REPO = Path(__file__).resolve().parents[1]
_API_JS = (_REPO / "web" / "static" / "js" / "api.js").read_text(encoding="utf-8")
_APP_JS = (_REPO / "web" / "static" / "js" / "app.js").read_text(encoding="utf-8")
_INDEX = (_REPO / "web" / "index.html").read_text(encoding="utf-8")


def test_terminal_action_calls_the_resume_endpoint_and_opens_the_child() -> None:
    assert "`/api/runs/${runId}/resume`" in _API_JS
    assert "performPaidRequest(() => api.resumeRun(sourceRunId)" in _APP_JS
    assert "openRun(accepted.run_id, { known: accepted })" in _APP_JS
    # Wrapping the call must preserve the endpoint and delivered child, not
    # merely satisfy a new spelling of the await expression.
    node = shutil.which("node")
    assert node, "Node is required for the resume delivery seam"
    result = subprocess.run([node, str(_REPO / "tests/js/composer_contract.mjs"), "resume_rerender"],
        capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS resume_rerender" in result.stdout


def test_byok_recovery_keeps_the_new_child_in_session_history() -> None:
    """Assert persisted child identity, not an inline spelling of the helper call."""
    node = shutil.which("node")
    assert node is not None, "Node is required for the shipped client contract."
    result = subprocess.run(
        [node, str(_REPO / "tests/js/composer_contract.mjs"), "accepted_history_success"],
        capture_output=True, text=True, encoding="utf-8", timeout=30, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS accepted_history_success" in result.stdout


def test_resume_button_depends_on_a_persisted_retrieval_checkpoint() -> None:
    assert 'checkpointing?.committed_nodes?.includes("retrieval")' in _APP_JS
    assert "paintActions(progress.state, progress.checkpointing)" in _APP_JS


def test_reuse_and_degradation_reach_the_visible_run_header() -> None:
    """A cache hit must not hide a simultaneous checkpoint write failure."""

    assert 'id="run-recovery"' in _INDEX
    assert 'recovery?.state === "reused"' in _APP_JS
    assert 'checkpointing?.state === "degraded"' in _APP_JS
    assert 'badges.join(" · ")' in _APP_JS
