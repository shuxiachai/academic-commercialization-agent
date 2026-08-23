"""Checkpoint persistence tests at the disk seam used by a restarted worker."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

import academic_agent.checkpoints as checkpoint_module
from academic_agent.checkpoints import (
    CheckpointIdentity,
    CheckpointInspection,
    CheckpointStore,
    CheckpointUsage,
    ModelIdentity,
    hash_bytes,
    hash_json,
    hash_text,
)


_COMPLETED_AT = datetime(2026, 8, 23, 12, 30, tzinfo=UTC)


def _identity(**changes: object) -> CheckpointIdentity:
    values: dict[str, object] = {
        "node_id": "writer",
        "input_sha256": hash_text("topic\npaper"),
        "evidence_sha256": hash_json({"academic": ["A1"], "patent": ["P1"]}),
        "config_sha256": hash_json({"prompt": "writer-v1", "language": "en"}),
        "upstream_sha256": {
            "academic": hash_text("academic output"),
            "patent": hash_text("patent output"),
            "market": hash_text("market output"),
        },
        "pipeline_revision": "f66f2e2",
        "as_of_date": date(2026, 8, 23),
        "model": ModelIdentity(
            provider="deepseek",
            model="deepseek-chat",
            endpoint_sha256=hash_text("https://api.deepseek.com"),
            temperature=0,
            response_format="text",
        ),
    }
    values.update(changes)
    return CheckpointIdentity.model_validate(values)


def _manifest_path(run_directory: Path) -> Path:
    return run_directory / "checkpoints" / "writer" / "manifest.json"


def test_hashes_are_full_stable_and_conservative() -> None:
    assert hash_bytes(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223"
        "b00361a396177a9cb410ff61f20015ad"
    )
    assert hash_text("line one\r\nline two\r") == hash_text("line one\nline two\n")
    assert hash_text("topic") != hash_text("topic ")
    assert hash_json({"b": 2, "a": 1}) == hash_json({"a": 1, "b": 2})
    assert hash_json(_identity()) == hash_json(_identity())
    with pytest.raises(ValueError):
        hash_json({"not_json": float("nan")})


def test_commit_is_reusable_after_a_fresh_process_reads_the_file_boundary(
    tmp_path: Path,
) -> None:
    identity = _identity()
    output = "# Commercialization report\n\nEvidence-backed conclusion.\n"
    usage = CheckpointUsage(
        prompt_tokens=120,
        completion_tokens=80,
        total_tokens=200,
        total_requests=1,
        cost_usd=0.0014,
        cost_complete=True,
    )

    manifest = CheckpointStore(tmp_path).commit(
        identity,
        output,
        output_format="markdown",
        usage=usage,
        completed_at=_COMPLETED_AT,
    )

    # Reconstructing the store is intentional: an in-memory cache could make
    # this pass while a restarted Railway worker still had nothing to resume.
    inspection = CheckpointStore(tmp_path).inspect(identity)
    assert inspection.state == "reusable"
    assert inspection.reasons == ()
    assert inspection.text() == output
    assert inspection.manifest == manifest
    assert manifest.status == "validated"
    assert manifest.output_file == f"output-{hash_bytes(output.encode())}.md"
    assert manifest.output_bytes == len(output.encode("utf-8"))
    assert manifest.usage == usage

    raw_manifest = _manifest_path(tmp_path).read_text(encoding="utf-8")
    assert "https://api.deepseek.com" not in raw_manifest
    assert "api_key" not in raw_manifest.lower()


def test_complete_but_stale_checkpoint_reports_each_identity_mismatch(
    tmp_path: Path,
) -> None:
    original = _identity()
    CheckpointStore(tmp_path).commit(original, "draft", output_format="text")

    alternatives = {
        "input_sha256": _identity(input_sha256=hash_text("different input")),
        "evidence_sha256": _identity(evidence_sha256=hash_text("different evidence")),
        "config_sha256": _identity(config_sha256=hash_text("different config")),
        "upstream_sha256": _identity(
            upstream_sha256={"academic": hash_text("different upstream")}
        ),
        "pipeline_revision": _identity(pipeline_revision="new-revision"),
        "as_of_date": _identity(as_of_date=date(2026, 8, 24)),
        "model": _identity(
            model=ModelIdentity(provider="openai", model="gpt-5", temperature=0)
        ),
    }
    for field_name, expected in alternatives.items():
        inspection = CheckpointStore(tmp_path).inspect(expected)
        assert inspection.state == "mismatch"
        assert inspection.reasons == (f"identity.{field_name}",)
        assert inspection.payload is None


def test_upstream_mapping_order_does_not_invalidate_the_same_dependencies(
    tmp_path: Path,
) -> None:
    first_order = {
        "academic": hash_text("A"),
        "patent": hash_text("P"),
        "market": hash_text("M"),
    }
    reverse_order = dict(reversed(list(first_order.items())))
    stored = _identity(upstream_sha256=first_order)
    expected = _identity(upstream_sha256=reverse_order)

    CheckpointStore(tmp_path).commit(stored, "report", output_format="text")

    assert hash_json(stored) == hash_json(expected)
    assert CheckpointStore(tmp_path).inspect(expected).state == "reusable"


def test_tampered_output_is_corrupt_not_a_cache_miss(tmp_path: Path) -> None:
    identity = _identity()
    manifest = CheckpointStore(tmp_path).commit(
        identity, "validated report", output_format="text"
    )
    output_path = _manifest_path(tmp_path).parent / manifest.output_file
    output_path.write_text("tampered report", encoding="utf-8")

    inspection = CheckpointStore(tmp_path).inspect(identity)

    assert inspection.state == "corrupt"
    assert inspection.reasons == ("output_bytes", "output_sha256")
    assert inspection.payload is None


def test_missing_output_is_corrupt_while_an_orphan_without_manifest_is_missing(
    tmp_path: Path,
) -> None:
    identity = _identity()
    manifest = CheckpointStore(tmp_path).commit(identity, "report", output_format="text")
    (_manifest_path(tmp_path).parent / manifest.output_file).unlink()
    assert CheckpointStore(tmp_path).inspect(identity).state == "corrupt"

    orphan_run = tmp_path / "orphan-run"
    orphan_directory = orphan_run / "checkpoints" / "writer"
    orphan_directory.mkdir(parents=True)
    orphan_directory.joinpath(f"output-{'0' * 64}.txt").write_text(
        "uncommitted", encoding="utf-8"
    )
    inspection = CheckpointStore(orphan_run).inspect(identity)
    assert inspection.state == "missing"
    assert inspection.reasons == ("manifest",)


def test_manifest_schema_and_identity_corruption_are_reported_explicitly(
    tmp_path: Path,
) -> None:
    identity = _identity()
    CheckpointStore(tmp_path).commit(identity, "report", output_format="text")
    manifest_path = _manifest_path(tmp_path)
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))

    raw["output_file"] = "../commercialization_report.md"
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")
    bad_path = CheckpointStore(tmp_path).inspect(identity)
    assert bad_path.state == "corrupt"
    assert bad_path.reasons == ("manifest_parse:ValidationError",)

    CheckpointStore(tmp_path).commit(identity, "report", output_format="text")
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw["output_file"] = f"output-{'0' * 64}.txt"
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")
    bad_content_address = CheckpointStore(tmp_path).inspect(identity)
    assert bad_content_address.state == "corrupt"
    assert bad_content_address.reasons == ("manifest_parse:ValidationError",)

    CheckpointStore(tmp_path).commit(identity, "report", output_format="text")
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw["identity"]["pipeline_revision"] = "tampered-revision"
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")
    bad_identity = CheckpointStore(tmp_path).inspect(identity)
    assert bad_identity.state == "corrupt"
    assert bad_identity.reasons == ("identity_sha256",)


def test_manifest_failure_preserves_the_previous_reusable_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The old manifest must never point at bytes overwritten by a failed commit."""

    store = CheckpointStore(tmp_path)
    old_identity = _identity()
    store.commit(old_identity, "old validated output", output_format="text")
    original_atomic_write = checkpoint_module._atomic_write_bytes

    def fail_manifest(path: Path, payload: bytes) -> None:
        if path.name == "manifest.json":
            raise OSError("injected manifest write failure")
        original_atomic_write(path, payload)

    monkeypatch.setattr(checkpoint_module, "_atomic_write_bytes", fail_manifest)
    with pytest.raises(OSError, match="injected manifest write failure"):
        store.commit(
            _identity(config_sha256=hash_text("new configuration")),
            "new output that must remain uncommitted",
            output_format="text",
        )

    # This is the recovery seam: a new process still sees the complete old
    # pair, while the newly written content-addressed file is only an orphan.
    inspection = CheckpointStore(tmp_path).inspect(old_identity)
    assert inspection.state == "reusable"
    assert inspection.text() == "old validated output"
    assert len(list(_manifest_path(tmp_path).parent.glob("output-*.txt"))) == 2


def test_failed_atomic_replace_cleans_its_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_replace(_source: Path, _destination: Path) -> None:
        raise OSError("injected replace failure")

    monkeypatch.setattr(checkpoint_module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="injected replace failure"):
        CheckpointStore(tmp_path).commit(_identity(), "report", output_format="text")

    node_directory = _manifest_path(tmp_path).parent
    assert not list(node_directory.glob(".*.tmp"))
    assert not _manifest_path(tmp_path).exists()


def test_contract_rejects_secrets_self_dependencies_and_naive_timestamps(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValidationError, match="api_key"):
        ModelIdentity(
            provider="deepseek",
            model="deepseek-chat",
            api_key="must-not-be-persisted",  # type: ignore[call-arg]
        )
    with pytest.raises(ValidationError, match="own output"):
        _identity(upstream_sha256={"writer": hash_text("self")})
    with pytest.raises(ValidationError, match="literal_error"):
        _identity(node_id="unknown")
    with pytest.raises(ValidationError, match="timezone"):
        CheckpointStore(tmp_path).commit(
            _identity(),
            "report",
            output_format="text",
            completed_at=datetime(2026, 8, 23, 12, 30),
        )
    assert not _manifest_path(tmp_path).exists()


def test_non_reusable_inspection_cannot_be_read_as_success() -> None:
    with pytest.raises(RuntimeError, match="missing, not reusable"):
        CheckpointInspection("missing", ("manifest",)).text()
