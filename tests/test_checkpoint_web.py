"""Browser seams for checkpoint recovery.

The backend tests prove reuse. These assertions prove the values and the new
child id reach the shipped client, which is where earlier features disappeared
despite being computed and stored correctly.
"""

from pathlib import Path


_REPO = Path(__file__).resolve().parents[1]
_API_JS = (_REPO / "web" / "static" / "js" / "api.js").read_text(encoding="utf-8")
_APP_JS = (_REPO / "web" / "static" / "js" / "app.js").read_text(encoding="utf-8")
_INDEX = (_REPO / "web" / "index.html").read_text(encoding="utf-8")


def test_terminal_action_calls_the_resume_endpoint_and_opens_the_child() -> None:
    assert "`/api/runs/${runId}/resume`" in _API_JS
    assert "const accepted = await api.resumeRun(sourceRunId)" in _APP_JS
    assert "openRun(accepted.run_id, { known: accepted })" in _APP_JS


def test_byok_recovery_keeps_the_new_child_in_session_history() -> None:
    assert "if (byokMode) api.addByokRun(accepted.run_id, accepted.topic)" in _APP_JS


def test_resume_button_depends_on_a_persisted_retrieval_checkpoint() -> None:
    assert 'checkpointing?.committed_nodes?.includes("retrieval")' in _APP_JS
    assert "paintActions(progress.state, progress.checkpointing)" in _APP_JS


def test_reuse_and_degradation_reach_the_visible_run_header() -> None:
    """A cache hit must not hide a simultaneous checkpoint write failure."""

    assert 'id="run-recovery"' in _INDEX
    assert 'recovery?.state === "reused"' in _APP_JS
    assert 'checkpointing?.state === "degraded"' in _APP_JS
    assert 'badges.join(" · ")' in _APP_JS
