"""What a resumed run says about itself while it runs and once it is done.

On 2026-11-18 a production run failed in scoring after 25 min 31 s and about
141,000 tokens; its resume finished in 3 min 48 s. The resume's public stage
read "Phase 1 — Evidence Collection" from its first second to its last, its
scoring time was filed under that stage, and its page gave only its own time
and tokens for a report that had taken both runs to produce.

These tests hold the three facts a reader now gets instead:

- the worker records the stage of the first task that really runs;
- the run reads carry the earlier runs' time and usage and the totals, with
  the usage completeness rule kept (a floor in any run makes the sum a floor);
- the run list names the run each resume continues.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import api.runs as runs
from academic_agent.checkpoint_runtime import TASK_NODES
from academic_agent.pipeline_worker import (
    _PARALLEL_COUNT,
    _PARALLEL_STAGE,
    _SEQUENTIAL_STAGES,
    _STAGE_INITIAL,
    ProgressTracker,
)
from academic_agent.run_spec import RESUME_SNAPSHOT_DIRECTORY
from academic_agent.run_terminal import TerminalRecord, UsageAccounting, commit_terminal_record
from api import access
from api.main import app
from tests.test_checkpoint_worker import _FakeCrew, _output, _source_collection


# ── The worker: which stage a resumed run says it is in ─────────────────────


class _WatchedCrew(_FakeCrew):
    """Notes the public stage at the moment each task really runs, and can stop before one."""

    def __init__(self, status_path: Path, *, stop_before: str | None = None) -> None:
        super().__init__()
        self.status_path = status_path
        self.stop_before = stop_before
        self.stage_when_run: dict[str, str] = {}

    def kickoff(self, *, inputs: dict[str, str]) -> SimpleNamespace:
        del inputs
        for node, task in zip(TASK_NODES, self.tasks, strict=True):
            if task.output is not None:
                continue
            if node == self.stop_before:
                raise RuntimeError("the provider stopped answering")
            self.stage_when_run[node] = json.loads(self.status_path.read_text(encoding="utf-8"))["stage"]
            output = _output(node)
            task.output = output
            self.executed.append(node)
            if task.callback is not None:
                task.callback(output)
            if self.task_callback is not None and self.task_callback is not task.callback:
                self.task_callback(output)
        outputs = [task.output for task in self.tasks]
        return SimpleNamespace(tasks_output=outputs, raw=outputs[-1].raw)


def _run_worker(output_root: Path, run_id: str, source_collection, crew: _FakeCrew, *,
                resume_from: str | None = None) -> Path:
    """The worker over a scripted crew, with the worker's own completion callback handed to it.

    The harness this is modelled on (tests/test_checkpoint_worker.py) drops
    that callback, which is what moves the public stage; here it is the
    thing under test.
    """
    argv = ["pipeline_worker.py", run_id, source_collection.topic]
    if resume_from is not None:
        argv += ["--resume-from", resume_from]

    def build(_collection, *, task_callback=None):
        crew.task_callback = task_callback
        # The public stage at the moment the crew is built: after the sources
        # are in, before any checkpoint has been read.
        crew.stage_at_build = json.loads((output_root / run_id / "status.json").read_text(encoding="utf-8"))["stage"]
        return SimpleNamespace(crew=lambda: crew)

    empty_usage = SimpleNamespace(agents=[], collection_error=None)
    with (
        patch.object(sys, "argv", argv),
        patch("academic_agent.run_output.DEFAULT_OUTPUT_ROOT", output_root),
        patch("academic_agent.source_pipeline.collect_source_collection", return_value=source_collection),
        patch("academic_agent.crew.AcademicAgent", side_effect=build),
        patch("academic_agent.token_usage.collect_usage", return_value=empty_usage),
    ):
        from academic_agent.pipeline_worker import main

        main()
    return output_root / run_id


def _stopped_parent(tmp_path: Path, *, stop_before: str) -> tuple[str, Path]:
    parent_id = "20260823T010101Z-resumeprogressparent"
    crew = _WatchedCrew(tmp_path / parent_id / "status.json", stop_before=stop_before)
    with pytest.raises(SystemExit):
        _run_worker(tmp_path, parent_id, _source_collection(), crew)
    return parent_id, tmp_path / parent_id


def _resume(tmp_path: Path, parent_id: str, parent_directory: Path) -> tuple[_WatchedCrew, dict]:
    child_id = "20260823T020202Z-resumeprogresschild"
    child_directory = tmp_path / child_id
    shutil.copytree(parent_directory / "checkpoints", child_directory / RESUME_SNAPSHOT_DIRECTORY / "checkpoints")
    crew = _WatchedCrew(child_directory / "status.json")
    _run_worker(tmp_path, child_id, _source_collection(), crew, resume_from=parent_id)
    return crew, json.loads((child_directory / "status.json").read_text(encoding="utf-8"))


def test_a_resume_with_only_scoring_left_says_scoring_while_it_scores(tmp_path: Path) -> None:
    parent_id, parent_directory = _stopped_parent(tmp_path, stop_before="scorer")
    crew, status = _resume(tmp_path, parent_id, parent_directory)

    assert crew.executed == ["scorer"]
    assert crew.stage_when_run == {"scorer": _SEQUENTIAL_STAGES[2]}
    # Until its checkpoints are read a resume does not know where it starts,
    # and does not claim the evidence stage in the meantime.
    assert crew.stage_at_build == _STAGE_INITIAL
    # The evidence, writing and review stages were never this run's: none has
    # a clock here, so no time of the scorer's is filed under another stage.
    assert [timing["stage"] for timing in status["stage_timings"]] == [_STAGE_INITIAL, _SEQUENTIAL_STAGES[2], "Done"]
    assert status["recovery"]["reused_nodes"] == ["retrieval", "academic", "patent", "market", "writer", "reviewer"]


def test_a_resume_from_the_writer_on_says_writing_then_review_then_scoring(tmp_path: Path) -> None:
    parent_id, parent_directory = _stopped_parent(tmp_path, stop_before="writer")
    crew, status = _resume(tmp_path, parent_id, parent_directory)

    assert crew.executed == ["writer", "reviewer", "scorer"]
    assert crew.stage_when_run == dict(zip(("writer", "reviewer", "scorer"), _SEQUENTIAL_STAGES, strict=True))
    assert [timing["stage"] for timing in status["stage_timings"]] == [_STAGE_INITIAL, *_SEQUENTIAL_STAGES, "Done"]


def test_a_resume_that_reuses_only_part_of_the_evidence_is_in_the_evidence_stage(tmp_path: Path) -> None:
    parent_id, parent_directory = _stopped_parent(tmp_path, stop_before="market")
    crew, status = _resume(tmp_path, parent_id, parent_directory)

    assert crew.executed == ["market", "writer", "reviewer", "scorer"]
    assert crew.stage_when_run["market"] == _PARALLEL_STAGE
    assert [timing["stage"] for timing in status["stage_timings"]] == [
        _STAGE_INITIAL, _PARALLEL_STAGE, *_SEQUENTIAL_STAGES, "Done"]


def test_a_fresh_run_still_enters_the_evidence_stage_before_its_crew_is_built(tmp_path: Path) -> None:
    run_id = "20260823T030303Z-resumeprogressfresh"
    crew = _WatchedCrew(tmp_path / run_id / "status.json")
    _run_worker(tmp_path, run_id, _source_collection(), crew)

    status = json.loads((tmp_path / run_id / "status.json").read_text(encoding="utf-8"))
    # With its sources in, a fresh run is in the evidence stage: the write
    # that carries the source counts says so, as it always has.
    assert crew.stage_at_build == _PARALLEL_STAGE
    assert crew.stage_when_run["academic"] == _PARALLEL_STAGE
    assert [timing["stage"] for timing in status["stage_timings"]] == [
        _STAGE_INITIAL, _PARALLEL_STAGE, *_SEQUENTIAL_STAGES, "Done"]


@pytest.mark.parametrize(("restored", "stage"), [
    (0, _PARALLEL_STAGE), (1, _PARALLEL_STAGE), (2, _PARALLEL_STAGE),
    (3, _SEQUENTIAL_STAGES[0]), (4, _SEQUENTIAL_STAGES[1]), (5, _SEQUENTIAL_STAGES[2]),
    # Everything restored: nothing is left to run, and the label stays the last stage's.
    (6, _SEQUENTIAL_STAGES[2]),
])
def test_the_stage_after_a_restored_prefix_is_the_next_tasks(restored: int, stage: str) -> None:
    tracker = ProgressTracker(_PARALLEL_COUNT, _SEQUENTIAL_STAGES, _PARALLEL_STAGE)
    tracker.restore_completed_prefix(restored)
    assert tracker.current_stage() == stage


def test_the_current_stage_follows_completions_as_the_callback_reports_them() -> None:
    tracker = ProgressTracker(_PARALLEL_COUNT, _SEQUENTIAL_STAGES, _PARALLEL_STAGE)
    for _ in range(_PARALLEL_COUNT + len(_SEQUENTIAL_STAGES) - 1):
        _, stage, _ = tracker.on_complete()
        assert tracker.current_stage() == stage


def test_the_worker_records_the_model_it_was_configured_with(tmp_path: Path, monkeypatch) -> None:
    for name in ("DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENAI_API_BASE", "OPENAI_MODEL_NAME"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "qwen")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "not-a-key")
    monkeypatch.setenv("QWEN_MODEL", "model-under-test")
    monkeypatch.setenv("QWEN_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    run_id = "20260823T040404Z-resumeprogressmodel"
    seen: dict[str, object] = {}

    class _Crew(_FakeCrew):
        def kickoff(self, *, inputs):
            # Before any agent has answered: the name is on record from the start.
            seen["model"] = json.loads((tmp_path / run_id / "status.json").read_text(encoding="utf-8")).get("llm_model")
            return super().kickoff(inputs=inputs)

    _run_worker(tmp_path, run_id, _source_collection(), _Crew())
    assert seen["model"] == "model-under-test"
    assert json.loads((tmp_path / run_id / "status.json").read_text(encoding="utf-8"))["llm_model"] == "model-under-test"


def test_a_worker_with_no_model_configured_records_none(tmp_path: Path, monkeypatch) -> None:
    for name in ("LLM_PROVIDER", "DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
                 "QWEN_MODEL", "OPENAI_MODEL_NAME"):
        monkeypatch.setenv(name, "")
    run_id = "20260823T050505Z-resumeprogressnomodel"
    _run_worker(tmp_path, run_id, _source_collection(), _FakeCrew())
    assert "llm_model" not in json.loads((tmp_path / run_id / "status.json").read_text(encoding="utf-8"))


# ── The run reads: earlier runs and totals ──────────────────────────────────

_START = datetime(2026, 11, 18, 9, tzinfo=UTC)


def _usage(tokens: int, *, cost: float | None = None, cost_complete: bool = True) -> dict:
    return {"total_tokens": tokens, "total_requests": 6, "cost_usd": cost, "cost_complete": cost_complete,
            "agents": [{"role": "Report Writer", "model": "model-a", "total_tokens": tokens}]}


@pytest.fixture
def root(tmp_path: Path):
    with patch.object(runs, "DEFAULT_OUTPUT_ROOT", tmp_path), patch.object(runs, "_registry", {}), \
            patch.object(access, "ACCESS_CODE", None), patch.object(access, "ACCESS_CODES", None), \
            patch.object(access, "ADMIN_CODE", None):
        yield tmp_path


def _run(root: Path, serial: int, *, state: str = "completed", elapsed: int = 100, usage: dict | None = None,
         usage_state: str | None = None, resumed: str | None = None, reused: tuple[str, ...] = ("retrieval",),
         topic: str = "sodium-ion storage") -> str:
    run_id = f"202611{serial:02d}T090000Z-" + f"{serial:x}" * 32
    run_dir = root / run_id
    run_dir.mkdir()
    recovery = {"state": "not_requested", "source_run_id": None, "reused_nodes": [], "next_node": "academic"}
    if resumed is not None:
        recovery = {"state": "reused", "source_run_id": resumed, "reused_nodes": list(reused), "next_node": None}
    status = {"stage": "Done" if state == "completed" else "Error", "done": True, "topic": topic,
              "error": None if state == "completed" else "boom", "recovery": recovery}
    (run_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
    if usage_state is None:
        usage_state = "unavailable" if usage is None else "complete" if state == "completed" else "lower_bound"
    end = _START + timedelta(seconds=elapsed)
    commit_terminal_record(run_dir, TerminalRecord(
        state=state, reason_code="worker_completed" if state == "completed" else "worker_exception",
        termination_method="worker_exit", started_at=_START, ended_at=end, elapsed_seconds=elapsed,
        last_stage=status["stage"], timeout_seconds=1800, usage=usage,
        usage_accounting=UsageAccounting(
            state=usage_state, snapshot_at=end, run_complete=usage_state == "complete",
            in_flight_request_may_have_spent=usage_state != "complete"),
        recovery=recovery,
    ))
    return run_id


def test_a_run_that_was_not_a_resume_has_no_lineage(root: Path) -> None:
    run_id = _run(root, 1, usage=_usage(50_000))
    assert runs.get_state(run_id)["lineage"] is None


def test_a_resume_adds_up_itself_and_the_run_it_continues(root: Path) -> None:
    """25:31 and at least 141,193 tokens, then 3:48 and 35,012: 29:19 and at least 176,205."""
    parent = _run(root, 1, state="failed", elapsed=1531, usage=_usage(141_193, cost=0.21))
    child = _run(root, 2, elapsed=228, usage=_usage(35_012, cost=0.05), resumed=parent)

    lineage = runs.get_state(child)["lineage"]
    assert lineage["earlier"] == [{
        "run_id": parent, "record": "available", "state": "failed", "elapsed_seconds": 1531,
        "total_tokens": 141_193, "usage_state": "lower_bound", "cost_usd": 0.21, "cost_complete": True,
    }]
    assert lineage["combined"] == {
        "runs": 2, "elapsed_seconds": 1759, "elapsed_complete": True, "total_tokens": 176_205,
        # The failed run's count is a floor (a request in flight is not free), so the sum is one.
        "usage_state": "lower_bound", "cost_usd": 0.26, "cost_complete": True,
    }


def test_the_total_is_complete_only_when_every_run_is(root: Path) -> None:
    parent = _run(root, 1, state="failed", usage=_usage(10, cost=0.01), usage_state="complete")
    child = _run(root, 2, usage=_usage(5, cost=0.01), resumed=parent)
    assert runs.get_state(child)["lineage"]["combined"]["usage_state"] == "complete"

    floor_child = _run(root, 3, usage=_usage(5), usage_state="lower_bound", resumed=parent)
    assert runs.get_state(floor_child)["lineage"]["combined"]["usage_state"] == "lower_bound"


def test_a_run_with_no_count_is_left_out_and_the_sum_is_a_floor(root: Path) -> None:
    parent = _run(root, 1, state="failed", elapsed=500, usage=None)
    child = _run(root, 2, elapsed=100, usage=_usage(5_000, cost=0.02), resumed=parent)

    lineage = runs.get_state(child)["lineage"]
    assert lineage["earlier"][0]["total_tokens"] is None
    assert lineage["earlier"][0]["usage_state"] == "unavailable"
    combined = lineage["combined"]
    assert (combined["total_tokens"], combined["usage_state"]) == (5_000, "lower_bound")
    # A price for one run of two is not the price of both.
    assert (combined["cost_usd"], combined["cost_complete"]) == (0.02, False)
    assert (combined["elapsed_seconds"], combined["elapsed_complete"]) == (600, True)


def test_an_old_record_with_a_count_and_no_accounting_is_a_floor(root: Path) -> None:
    """A run from before terminal records: its count is what was seen, and nothing says it was everything."""
    parent = "20261101T090000Z-" + "9" * 32
    (root / parent).mkdir()
    (root / parent / "status.json").write_text(json.dumps({
        "stage": "Error", "done": False, "error": "boom", "topic": "t", "usage": _usage(7_000),
    }), encoding="utf-8")
    child = _run(root, 2, usage=_usage(5_000), resumed=parent)
    lineage = runs.get_state(child)["lineage"]
    assert (lineage["earlier"][0]["total_tokens"], lineage["earlier"][0]["usage_state"]) == (7_000, "lower_bound")
    assert (lineage["combined"]["total_tokens"], lineage["combined"]["usage_state"]) == (12_000, "lower_bound")


def test_a_collector_that_failed_left_a_default_not_a_count(root: Path) -> None:
    """Its zero is where a number would have been: left out, never added as nothing spent."""
    parent = _run(root, 1, state="failed", usage={"total_tokens": 0, "collection_error": "collector raised"},
                  usage_state="unavailable")
    child = _run(root, 2, usage=_usage(5_000), resumed=parent)
    lineage = runs.get_state(child)["lineage"]
    assert lineage["earlier"][0]["total_tokens"] is None
    assert lineage["earlier"][0]["usage_state"] == "unavailable"
    assert (lineage["combined"]["total_tokens"], lineage["combined"]["usage_state"]) == (5_000, "lower_bound")


def test_no_count_anywhere_is_unavailable_not_zero(root: Path) -> None:
    parent = _run(root, 1, state="failed", usage=None)
    child = _run(root, 2, usage=None, resumed=parent)
    combined = runs.get_state(child)["lineage"]["combined"]
    assert (combined["total_tokens"], combined["usage_state"], combined["cost_usd"]) == (None, "unavailable", None)


def test_an_earlier_run_that_was_deleted_is_named_as_missing(root: Path) -> None:
    parent = _run(root, 1, state="failed", elapsed=500, usage=_usage(9_000))
    child = _run(root, 2, elapsed=100, usage=_usage(5_000), resumed=parent)
    shutil.rmtree(root / parent)

    lineage = runs.get_state(child)["lineage"]
    assert lineage["earlier"] == [{"run_id": parent, "record": "missing"}]
    combined = lineage["combined"]
    assert (combined["elapsed_seconds"], combined["elapsed_complete"]) == (100, False)
    assert (combined["total_tokens"], combined["usage_state"]) == (5_000, "lower_bound")


def test_a_resume_of_a_resume_counts_all_three(root: Path) -> None:
    first = _run(root, 1, state="failed", elapsed=300, usage=_usage(1_000))
    second = _run(root, 2, state="failed", elapsed=200, usage=_usage(2_000), resumed=first)
    third = _run(root, 3, elapsed=100, usage=_usage(4_000), resumed=second)

    lineage = runs.get_state(third)["lineage"]
    assert [row["run_id"] for row in lineage["earlier"]] == [second, first]
    assert (lineage["combined"]["runs"], lineage["combined"]["elapsed_seconds"],
            lineage["combined"]["total_tokens"]) == (3, 600, 7_000)


def test_a_source_that_does_not_come_before_its_child_is_not_followed(root: Path) -> None:
    """A run id begins with its start time. A record naming itself, or a later run, is damaged."""
    later = _run(root, 5, state="failed", usage=_usage(1))
    child = _run(root, 2, usage=_usage(1), resumed=later)
    assert runs.get_state(child)["lineage"] is None
    own = _run(root, 6, usage=_usage(1))
    status_path = root / own / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status["recovery"] = {"state": "reused", "source_run_id": own, "reused_nodes": ["retrieval"], "next_node": None}
    status_path.write_text(json.dumps(status), encoding="utf-8")
    assert runs.resumed_from(status["recovery"], own) is None
    assert runs.resumed_from({"source_run_id": "../../etc"}, own) is None
    assert runs.resumed_from(None, own) is None


def test_the_look_back_is_bounded(root: Path) -> None:
    previous = _run(root, 1, state="failed", usage=_usage(1))
    for serial in range(2, 13):
        previous = _run(root, serial, state="failed" if serial < 12 else "completed", usage=_usage(1),
                        resumed=previous)
    lineage = runs.get_state(previous)["lineage"]
    assert len(lineage["earlier"]) == runs._LINEAGE_DEPTH


def test_both_run_reads_carry_the_lineage_whole(root: Path) -> None:
    """The seam: a response model drops what it does not declare, and one read names each field."""
    parent = _run(root, 1, state="failed", elapsed=1531, usage=_usage(141_193, cost=0.21))
    child = _run(root, 2, elapsed=228, usage=_usage(35_012, cost=0.05), resumed=parent)
    expected = runs.get_state(child)["lineage"]
    client = TestClient(app)
    for path in (f"/api/runs/{child}", f"/api/runs/{child}/progress"):
        assert client.get(path).json()["lineage"] == expected, path
    for path in (f"/api/runs/{parent}", f"/api/runs/{parent}/progress"):
        assert client.get(path).json()["lineage"] is None, path


# ── The other direction: the run that continued this one ────────────────────


def _resumed_child(root: Path, serial: int, parent: str, *, owner: str | None = None, **more) -> str:
    """A run resumed from `parent`, with the snapshot the API takes for every resume."""
    child = _run(root, serial, resumed=parent, usage=_usage(1), **more)
    (root / child / runs.RESUME_SNAPSHOT_DIRECTORY / "checkpoints").mkdir(parents=True)
    if owner is not None:
        (root / child / ".owner").write_text(owner, encoding="utf-8")
    return child


def test_a_stopped_run_names_the_newest_run_that_continued_it(root: Path) -> None:
    parent = _run(root, 1, state="failed", usage=_usage(1))
    assert runs.continued_by(parent) is None
    first = _resumed_child(root, 2, parent, state="failed")
    assert runs.continued_by(parent) == first
    second = _resumed_child(root, 3, parent)
    assert runs.continued_by(parent) == second
    # A resume of the first resume continues that one, not the run before it.
    third = _resumed_child(root, 4, first)
    assert runs.continued_by(first) == third
    assert runs.continued_by(parent) == second
    assert runs.continued_by(third) is None


def test_only_a_run_with_the_resume_snapshot_and_the_same_owner_counts(root: Path) -> None:
    alice, bob = access.owner_id("for-alice"), access.owner_id("for-bob")
    parent = _run(root, 1, state="failed", usage=_usage(1))
    (root / parent / ".owner").write_text(alice, encoding="utf-8")
    # Says it continues the parent, under the same owner, and has no snapshot:
    # not a resume the API launched.
    unsnapshotted = _run(root, 2, resumed=parent, usage=_usage(1))
    (root / unsnapshotted / ".owner").write_text(alice, encoding="utf-8")
    assert runs.continued_by(parent) is None
    # Someone else's resume of it (an administrator's, say) is theirs to open, not the owner's.
    _resumed_child(root, 3, parent, owner=bob)
    assert runs.continued_by(parent) is None
    own = _resumed_child(root, 4, parent, owner=alice)
    assert runs.continued_by(parent) == own
    assert runs.continued_by("../outside") is None
    assert runs.continued_by("20260101T000000Z-" + "0" * 32) is None


def test_a_child_whose_status_cannot_be_read_is_passed_over(root: Path) -> None:
    parent = _run(root, 1, state="failed", usage=_usage(1))
    good = _resumed_child(root, 2, parent)
    broken = _resumed_child(root, 3, parent)
    (root / broken / "status.json").write_bytes(b"{broken")
    assert runs.continued_by(parent) == good


def test_both_run_reads_tell_whoever_may_modify_the_run_and_nobody_else(root: Path) -> None:
    """Naming a run hands over its link. A reader of a failed run is not given its resume's report."""
    alice = access.owner_id("for-alice")
    parent = _run(root, 1, state="failed", usage=_usage(1))
    (root / parent / ".owner").write_text(alice, encoding="utf-8")
    child = _resumed_child(root, 2, parent, owner=alice)
    ownerless = _run(root, 3, state="failed", usage=_usage(1))
    _resumed_child(root, 4, ownerless)
    with patch.object(access, "ACCESS_CODES", "for-alice,for-bob"), patch.object(access, "ADMIN_CODE", "for-admin"):
        client = TestClient(app)
        for path in (f"/api/runs/{parent}", f"/api/runs/{parent}/progress"):
            told = {who: client.get(path, headers=headers).json()["continued_by"] for who, headers in (
                ("owner", {"X-Access-Code": "for-alice"}), ("administrator", {"X-Access-Code": "for-admin"}),
                ("another code", {"X-Access-Code": "for-bob"}), ("no code", {}))}
            assert told == {"owner": child, "administrator": child, "another code": None, "no code": None}, path
        # A run with no owner on record: the server cannot say who is asking, and names nothing.
        for headers in ({}, {"X-Access-Code": "for-alice"}):
            assert client.get(f"/api/runs/{ownerless}", headers=headers).json()["viewer_can_modify"] is None
            assert client.get(f"/api/runs/{ownerless}", headers=headers).json()["continued_by"] is None
        # The run that continued it has not been continued itself, and a finished run cannot be.
        assert client.get(f"/api/runs/{child}", headers={"X-Access-Code": "for-alice"}).json()["continued_by"] is None


def test_only_a_run_that_stopped_is_looked_up(root: Path) -> None:
    done = _run(root, 1, usage=_usage(1))
    _resumed_child(root, 2, done)       # a record that says so; a completed run cannot be resumed
    client = TestClient(app)
    assert runs.continued_by(done) is not None
    for path in (f"/api/runs/{done}", f"/api/runs/{done}/progress"):
        assert client.get(path).json()["continued_by"] is None, path
    stopped = _run(root, 3, state="failed", usage=_usage(1))
    resumed = _resumed_child(root, 4, stopped)
    for path in (f"/api/runs/{stopped}", f"/api/runs/{stopped}/progress"):
        assert client.get(path).json()["continued_by"] == resumed, path


def test_it_is_about_the_caller_and_not_part_of_the_runs_state(root: Path) -> None:
    parent = _run(root, 1, state="failed", usage=_usage(1))
    _resumed_child(root, 2, parent)
    assert "continued_by" not in runs.get_state(parent)


def test_the_run_list_names_the_run_each_resume_continues(root: Path) -> None:
    parent = _run(root, 1, state="failed", usage=_usage(1))
    child = _run(root, 2, usage=_usage(1), resumed=parent)
    alone = _run(root, 3, usage=_usage(1))
    listed = {row["run_id"]: row["resumed_from"] for row in TestClient(app).get("/api/runs").json()["runs"]}
    assert listed == {parent: None, child: parent, alone: None}
