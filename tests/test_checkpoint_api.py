"""HTTP recovery tests at the paid-operation and filesystem seams.

No provider or worker process is started. The source and checkpoint files are
real so the test proves an accepted child owns an immutable snapshot rather
than retaining a path to a parent that can disappear.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from academic_agent.checkpoint_runtime import retrieval_identity
from academic_agent.checkpoints import CheckpointStore
from academic_agent.run_spec import RESUME_SNAPSHOT_DIRECTORY, RunSpec
from api import access, runs
from api.main import app


def _run_id(suffix: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{suffix}"


@pytest.fixture
def recovery_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    monkeypatch.setattr(runs, "DEFAULT_OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(access, "ACCESS_CODE", None)
    monkeypatch.setattr(access, "ACCESS_CODES", None)
    runs._registry.clear()
    runs._inline_paid_operations.clear()
    yield TestClient(app)
    runs.shutdown_all()
    runs._registry.clear()
    runs._inline_paid_operations.clear()


def _failed_source(
    root: Path,
    *,
    suffix: str = "checkpointsource",
    with_checkpoint: bool = True,
    state: str = "failed",
) -> tuple[str, Path, RunSpec]:
    run_id = _run_id(suffix)
    run_directory = root / run_id
    run_directory.mkdir(parents=True)
    spec = RunSpec(
        topic="solid-state battery recycling",
        language="Simplified Chinese",
        weight_profile="clean_tech",
    )
    spec.save(run_directory)
    status = {
        "topic": spec.topic,
        "stage": "Error" if state == "failed" else "Done",
        "done": True,
        "error": "injected crash" if state == "failed" else None,
    }
    (run_directory / "status.json").write_text(json.dumps(status), encoding="utf-8")
    if with_checkpoint:
        CheckpointStore(run_directory).commit(
            retrieval_identity(
                spec,
                revision="git:abcdef0123456789",
                as_of_date=date(2026, 8, 23),
            ),
            '{"topic":"solid-state battery recycling"}',
            output_format="json",
        )
    return run_id, run_directory, spec


def _live_process() -> MagicMock:
    process = MagicMock()
    process.poll.return_value = None
    process.wait.return_value = 0
    return process


def test_resume_endpoint_snapshots_parent_before_starting_worker(
    recovery_client: TestClient,
    tmp_path: Path,
) -> None:
    source_id, source_directory, spec = _failed_source(tmp_path)
    process = _live_process()

    with patch("api.runs.subprocess.Popen", return_value=process) as popen:
        response = recovery_client.post(f"/api/runs/{source_id}/resume", json={})

    assert response.status_code == 202
    body = response.json()
    assert body["state"] == "running"
    assert body["topic"] == spec.topic
    assert body["resumed_from"] == source_id
    child_directory = tmp_path / body["run_id"]
    snapshot_manifest = child_directory / RESUME_SNAPSHOT_DIRECTORY / "checkpoints" / "retrieval" / "manifest.json"
    assert snapshot_manifest.is_file()
    assert RunSpec.load(child_directory) == spec

    command = popen.call_args.args[0]
    assert command[command.index("--resume-from") + 1] == source_id
    assert "--run-spec" in command

    # This is the race the snapshot exists to close. Once the API has returned
    # 202, deleting the failed parent must not invalidate the child's inputs.
    shutil.rmtree(source_directory)
    assert snapshot_manifest.is_file()


def test_resume_rejects_completed_unknown_or_pre_checkpoint_runs_without_spawning(
    recovery_client: TestClient,
    tmp_path: Path,
) -> None:
    completed_id, _, _ = _failed_source(tmp_path, suffix="completedsource", state="completed")
    old_id, _, _ = _failed_source(tmp_path, suffix="oldsource", with_checkpoint=False)
    unknown_id, unknown_directory, _ = _failed_source(tmp_path, suffix="unknownsource")
    # Unknown explicitly means the status may merely be unreadable while the
    # original run actually completed. Recovery must not turn that ambiguity
    # into a second paid run.
    (unknown_directory / "status.json").write_text("{", encoding="utf-8")

    with patch("api.runs.subprocess.Popen") as popen:
        completed = recovery_client.post(f"/api/runs/{completed_id}/resume", json={})
        old = recovery_client.post(f"/api/runs/{old_id}/resume", json={})
        unknown = recovery_client.post(f"/api/runs/{unknown_id}/resume", json={})

    assert completed.status_code == 409
    assert old.status_code == 409
    assert unknown.status_code == 409
    popen.assert_not_called()


def test_resume_byok_secrets_reach_env_not_argv_or_snapshot(
    recovery_client: TestClient,
    tmp_path: Path,
) -> None:
    source_id, _, _ = _failed_source(tmp_path, suffix="byoksource")
    process = _live_process()
    body = {
        "llm_provider": "deepseek",
        "llm_api_key": "fresh-llm-secret",
        "serper_api_key": "fresh-search-secret",
    }

    with patch("api.runs.subprocess.Popen", return_value=process) as popen:
        response = recovery_client.post(f"/api/runs/{source_id}/resume", json=body)

    assert response.status_code == 202
    command = popen.call_args.args[0]
    environment = popen.call_args.kwargs["env"]
    assert "fresh-llm-secret" not in " ".join(command)
    assert "fresh-search-secret" not in " ".join(command)
    assert environment["DEEPSEEK_API_KEY"] == "fresh-llm-secret"
    assert environment["SERPER_API_KEY"] == "fresh-search-secret"
    child_directory = tmp_path / response.json()["run_id"]
    persisted = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in child_directory.rglob("*")
        if path.is_file() and path.name != "process.log"
    )
    assert "fresh-llm-secret" not in persisted
    assert "fresh-search-secret" not in persisted


def test_checkpoint_and_recovery_fields_reach_both_status_endpoints(
    recovery_client: TestClient,
    tmp_path: Path,
) -> None:
    run_id = _run_id("statusseam")
    run_directory = tmp_path / run_id
    run_directory.mkdir()
    checkpointing = {
        "state": "degraded",
        "committed_nodes": ["retrieval", "academic"],
        "errors": ["patent:commit:OSError:disk full"],
    }
    recovery = {
        "state": "reused",
        "source_run_id": "parent",
        "reused_nodes": ["retrieval", "academic"],
        "next_node": "patent",
        "inspections": {},
    }
    (run_directory / "status.json").write_text(
        json.dumps(
            {
                "topic": "checkpoint seam",
                "stage": "Error",
                "done": True,
                "error": "injected",
                "checkpointing": checkpointing,
                "recovery": recovery,
            }
        ),
        encoding="utf-8",
    )

    status = recovery_client.get(f"/api/runs/{run_id}").json()
    progress = recovery_client.get(f"/api/runs/{run_id}/progress").json()

    assert status["checkpointing"] == checkpointing
    assert progress["checkpointing"] == checkpointing
    assert status["recovery"] == recovery
    assert progress["recovery"] == recovery


def test_owned_source_cannot_be_resumed_from_a_leaked_capability_url(
    recovery_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_id, source_directory, _ = _failed_source(tmp_path, suffix="ownedsource")
    owner = access.owner_id("alice-code")
    (source_directory / runs._OWNER_FILE).write_text(owner, encoding="utf-8")
    monkeypatch.setattr(access, "ACCESS_CODE", "alice-code")
    monkeypatch.setattr(access, "ACCESS_CODES", None)
    process = _live_process()
    byok = {
        "llm_provider": "deepseek",
        "llm_api_key": "attacker-key",
        "serper_api_key": "attacker-search",
    }

    with patch("api.runs.subprocess.Popen", return_value=process) as popen:
        denied = recovery_client.post(f"/api/runs/{source_id}/resume", json=byok)
        allowed = recovery_client.post(
            f"/api/runs/{source_id}/resume",
            json={},
            headers={"X-Access-Code": "alice-code"},
        )

    assert denied.status_code == 404
    assert allowed.status_code == 202
    popen.assert_called_once()
