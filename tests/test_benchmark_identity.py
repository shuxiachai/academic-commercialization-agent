"""Exercise accepted batch -> real run_topic -> stored artifacts -> summary.

Only the Crew's paid execution is replaced. Frozen public evidence, identity
hashing, CLI argument routing and filesystem acceptance remain real. Reuse
assertions count kickoff calls instead of looking for function names in source.
"""

import csv
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import benchmark
import benchmark_check
import benchmark_identity as identity
from academic_agent import crew, llm_config, pipeline_worker, run_output


@pytest.fixture
def harness(tmp_path, monkeypatch):
    monkeypatch.setattr(identity, "BATCH_ROOT", tmp_path / "batches")
    config = SimpleNamespace(provider="qwen", model="qwen3.5-plus", base_url="https://example.test/v1", api_key="do-not-persist-this-key")
    monkeypatch.setattr(llm_config, "resolve_provider_config", lambda: config)
    monkeypatch.setenv("LLM_PRICE_PER_MTOK", "")
    # Artifact production is real; only paid execution and irrelevant prose
    # generation are fake. No test invokes live source collection.
    kickoff = Mock(return_value=SimpleNamespace(tasks_output=[], raw="unused"))
    fake_crew = SimpleNamespace(kickoff=kickoff, agents=[])
    monkeypatch.setattr(crew, "AcademicAgent", lambda _: SimpleNamespace(crew=lambda: fake_crew))
    monkeypatch.setattr(run_output, "save_evidence_reports", lambda *a, **k: None)
    monkeypatch.setattr(run_output, "save_claim_grounding", lambda *a, **k: None)
    monkeypatch.setattr(pipeline_worker, "_select_report_and_scores", lambda *a: (
        "# Synthetic report", json.dumps({"trl_score": 5, "overall_score": 50})))
    selected = [(*benchmark.TOPICS[0], 1)]
    batch = identity.prepare_batch(selected, True, experiment_id="offline-test")
    return SimpleNamespace(root=tmp_path, selected=selected, batch=batch, config=config, kickoff=kickoff)


def run(h, *, force=False):
    num, topic, trl, industry, rep = h.selected[0]
    return benchmark.run_topic(num, topic, trl, industry, rep=rep, use_fixture=True,
                               force=force, batch=h.batch)


def test_success_is_reused_without_second_kickoff_and_without_byte_changes(harness):
    """A lost CLI session may reuse committed success, never spend again."""
    h = harness
    result = run(h)
    directory = Path(result["run_dir"])
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    assert result["status"] == "success"
    assert result["execution_identity"]["batch_sha256"] == h.batch["identity_sha256"]
    assert "evidence_sha256" in result
    assert run(h)["skipped"] is True
    assert h.kickoff.call_count == 1
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == before


@pytest.mark.parametrize("change", ["model", "endpoint", "settings", "fixture", "code", "dependencies"])
def test_changed_execution_identity_blocks_before_kickoff(harness, monkeypatch, change):
    """A known success cannot certify a different model/config/fixture checkout."""
    h = harness
    before = (Path(h.batch["root"]) / "batch.json").read_bytes()
    if change == "model":
        h.config.model = "different-model"
    elif change == "endpoint":
        h.config.base_url = "https://other.test/v1"
    elif change == "settings":
        monkeypatch.setenv("MAX_RPM", "77")
    else:
        original = identity.execution_identity
        def changed(*args):
            data = original(*args)
            field = {"fixture": "fixture_sha256", "code": "source_hashes",
                     "dependencies": "installed_versions"}[change]
            data[field] = {"changed": "f" * 64}
            return data
        monkeypatch.setattr(identity, "execution_identity", changed)
    with pytest.raises(ValueError, match="identity changed"):
        run(h)
    assert h.kickoff.call_count == 0
    assert (Path(h.batch["root"]) / "batch.json").read_bytes() == before


@pytest.mark.parametrize("fault", ["modified", "missing", "legacy", "failed", "force"])
def test_occupied_invalid_result_is_never_overwritten_or_automatically_retried(harness, fault):
    """Corruption is not authorization to pay for a replacement report."""
    h = harness
    result = run(h)
    directory = Path(result["run_dir"])
    if fault == "modified":
        (directory / "commercialization_report.md").write_text("changed", encoding="utf-8")
    elif fault == "missing":
        (directory / "commercialization_scores.json").unlink()
    elif fault in {"legacy", "failed"}:
        meta = json.loads((directory / "meta.json").read_text(encoding="utf-8"))
        if fault == "legacy":
            meta.pop("execution_identity")
        else:
            meta["status"] = "error_crew"
        (directory / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    with pytest.raises(ValueError, match="cannot be overwritten"):
        run(h, force=fault == "force")
    assert h.kickoff.call_count == 1
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == before


def test_batch_resume_is_explicit_and_checks_selected_cases(harness):
    h = harness
    with pytest.raises(FileExistsError):
        identity.prepare_batch(h.selected, True, experiment_id="offline-test")
    restored = identity.prepare_batch(h.selected, True, experiment_id="offline-test", resume=True)
    assert restored == h.batch
    changed = [(*benchmark.TOPICS[1], 1)]
    with pytest.raises(ValueError, match="identity changed"):
        identity.prepare_batch(changed, True, experiment_id="offline-test", resume=True)


def test_manifest_never_persists_credentials_and_new_batch_preserves_prior(harness, monkeypatch):
    h = harness
    monkeypatch.setenv("OPENAI_API_KEY", "second-secret-never-recorded")
    monkeypatch.setenv("ACCESS_CODE", "owner-secret")
    new = identity.prepare_batch(h.selected, True, experiment_id="new-measurement")
    raw = (Path(new["root"]) / "batch.json").read_text(encoding="utf-8")
    assert "do-not-persist-this-key" not in raw
    assert "second-secret-never-recorded" not in raw
    assert "owner-secret" not in raw
    assert (Path(h.batch["root"]) / "batch.json").exists()
    assert new["root"] != h.batch["root"]


@pytest.mark.parametrize("value", ["../archive", "..", "a/b", "a\\b", "x" * 81])
def test_batch_id_cannot_escape_its_root(harness, value):
    with pytest.raises(ValueError, match="slug"):
        identity.prepare_batch(harness.selected, True, experiment_id=value)


def test_unaccepted_direct_unit_fails_before_paid_calls(harness):
    num, topic, trl, industry, _ = harness.selected[0]
    with pytest.raises(ValueError, match="accepted versioned batch"):
        benchmark.run_topic(num, topic, trl, industry, use_fixture=True)
    harness.kickoff.assert_not_called()


def test_new_batch_summary_carries_identity_and_does_not_modify_results(harness):
    h = harness
    result = run(h)
    before = identity.result_hashes(Path(result["run_dir"]))
    destination = h.root / "summary"
    benchmark_check.main(Path(h.batch["root"]), destination)
    with (destination / "benchmark_summary.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["batch_sha256"] == h.batch["identity_sha256"]
    assert rows[0]["model"] == h.config.model
    assert identity.result_hashes(Path(result["run_dir"])) == before
    with pytest.raises(FileExistsError):
        benchmark_check.main(Path(h.batch["root"]), destination)


def test_summary_rejects_foreign_batch_before_publishing_csv(harness):
    h = harness
    result = run(h)
    path = Path(result["run_dir"]) / "meta.json"
    meta = json.loads(path.read_text(encoding="utf-8"))
    meta["execution_identity"]["batch_sha256"] = "0" * 64
    path.write_text(json.dumps(meta), encoding="utf-8")
    output = h.root / "summary"
    with pytest.raises(ValueError, match="different batch"):
        benchmark_check.main(Path(h.batch["root"]), output)
    assert not (output / "benchmark_summary.csv").exists()


def test_cli_routes_force_to_fresh_batch_and_resume_excludes_old_cost(harness, monkeypatch, capsys):
    """Exercise CLI control flow, not a source-text claim about cost accounting."""
    h = harness
    monkeypatch.setattr(benchmark, "TOPICS", [benchmark.TOPICS[0]])
    monkeypatch.setattr(benchmark, "_INTER_RUN_PAUSE", 0)
    monkeypatch.setattr("sys.argv", ["benchmark.py", "--fixtures", "--force", "--experiment-id", "cli-new"])
    benchmark.main()
    assert h.kickoff.call_count == 1
    root = identity.BATCH_ROOT / "cli-new"
    unit = next(p for p in root.iterdir() if p.is_dir())
    meta = json.loads((unit / "meta.json").read_text(encoding="utf-8"))
    meta["usage"] = {"cost_usd": 7, "total_tokens": 500, "cost_complete": True}
    (unit / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    capsys.readouterr()
    monkeypatch.setattr("sys.argv", ["benchmark.py", "--fixtures", "--resume-batch", "cli-new"])
    benchmark.main()
    out = capsys.readouterr().out
    assert "Every topic was skipped" in out
    assert "$7.0000" not in out
    assert h.kickoff.call_count == 1


def test_cli_force_cannot_reopen_existing_batch(harness, monkeypatch):
    h = harness
    monkeypatch.setattr(benchmark, "TOPICS", [benchmark.TOPICS[0]])
    monkeypatch.setattr("sys.argv", ["benchmark.py", "--fixtures", "--force", "--experiment-id", "offline-test"])
    with pytest.raises(SystemExit):
        benchmark.main()
    h.kickoff.assert_not_called()


def test_worker_rejects_manifest_changed_after_acceptance(harness):
    h = harness
    path = Path(h.batch["root"]) / "batch.json"
    changed = deepcopy(h.batch["identity"])
    changed["model"] = "changed-on-disk"
    path.write_text(json.dumps({"identity": changed, "identity_sha256": identity.json_digest(changed)}), encoding="utf-8")
    with pytest.raises(ValueError, match="identity changed"):
        run(h)
    h.kickoff.assert_not_called()


def test_source_bytes_and_raw_fixture_bytes_change_the_real_identity(harness, monkeypatch):
    """Verify the producer's hash, not only rejection of a fake identity field."""
    import benchmark_fixtures
    h = harness
    original = Path.read_bytes
    fixture = benchmark_fixtures.fixture_path(h.selected[0][0], benchmark._slug(h.selected[0][1]))
    for target in (identity.ROOT / "src" / "academic_agent" / "crew.py", fixture):
        with monkeypatch.context() as scoped:
            scoped.setattr(Path, "read_bytes", lambda path, bound=target: original(path) + (b"\n" if path == bound else b""))
            with pytest.raises(ValueError, match="identity changed"):
                run(h)
    h.kickoff.assert_not_called()


def test_missing_later_fixture_blocks_batch_before_any_paid_unit(harness, monkeypatch):
    """Discover a missing case before spending on earlier cases in that batch."""
    import benchmark_fixtures
    original = benchmark_fixtures.load
    monkeypatch.setattr(benchmark_fixtures, "load", lambda num, slug: None if num == "02" else original(num, slug))
    with pytest.raises(ValueError, match="Missing fixture"):
        identity.prepare_batch([(*benchmark.TOPICS[0], 1), (*benchmark.TOPICS[1], 1)],
                               True, experiment_id="missing-input")
    assert not (identity.BATCH_ROOT / "missing-input").exists()
    harness.kickoff.assert_not_called()
