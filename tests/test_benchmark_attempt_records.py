"""A benchmark unit keeps every provider attempt in meta.json, by agent.

The benchmark runs the crew in-process and writes no steps.jsonl, so until
now a batch could not say whether a slow unit was a slow model or a stalled
request retried. The 2026-11-09 production run showed 72% of its wall time
in stalled non-streaming attempts; the streaming change is validated by a
benchmark batch, which therefore needs the same per-attempt record the worker
has. Only the Crew's paid execution and live retrieval are replaced here;
run_topic is real.
"""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import benchmark
import benchmark_fixtures
import benchmark_identity as identity
from academic_agent import crew, llm_config, source_pipeline

ROLES = ("Academic", "Patent", "Market", "Writer", "Reviewer", "Scorer")


@pytest.fixture
def live(tmp_path, monkeypatch):
    monkeypatch.setattr(identity, "BATCH_ROOT", tmp_path / "batches")
    config = SimpleNamespace(provider="qwen", model="qwen3.5-plus",
                             base_url="https://example.test/v1", api_key="unused")
    monkeypatch.setattr(llm_config, "resolve_provider_config", lambda: config)
    num, topic, *_ = benchmark.TOPICS[0]
    monkeypatch.setattr(
        source_pipeline, "collect_source_collection",
        lambda _topic: benchmark_fixtures.load(num, benchmark._slug(topic)),
    )
    # Real wrapped providers (so the stage label has somewhere to live) whose
    # calls never leave the process.
    agents = [
        SimpleNamespace(
            role=role,
            llm=llm_config._wrap_with_retry(SimpleNamespace(call=lambda *a, **k: "x")),
        )
        for role in ROLES
    ]

    def kickoff(**_kwargs):
        stage = agents[3].llm._academic_agent_call_budget.stage
        llm_config._report_attempt({
            "stage": stage, "call": 1, "attempt": 1, "outcome": "timeout",
            "duration_seconds": 61.0, "retry": True, "error_type": "ConnectionError",
        })
        llm_config._report_attempt({
            "stage": stage, "call": 1, "attempt": 2, "outcome": "returned",
            "duration_seconds": 95.0, "retry": False, "error_type": None,
        })
        return SimpleNamespace(tasks_output=[], raw="unused")

    monkeypatch.setattr(
        crew, "AcademicAgent",
        lambda _collection: SimpleNamespace(crew=lambda: SimpleNamespace(kickoff=kickoff, agents=agents)),
    )
    selected = [(*benchmark.TOPICS[0], 1)]
    batch = identity.prepare_batch(selected, False, experiment_id="attempt-records")
    return SimpleNamespace(selected=selected, batch=batch, agents=agents)


def test_each_provider_attempt_is_kept_in_meta_with_its_agent(live):
    num, topic, trl, industry, rep = live.selected[0]

    meta = benchmark.run_topic(num, topic, trl, industry, rep=rep, batch=live.batch)

    saved = json.loads((Path(meta["run_dir"]) / "meta.json").read_text(encoding="utf-8"))
    assert [
        (a["agent"], a["call"], a["attempt"], a["outcome"], a["duration_seconds"], a["retry"])
        for a in saved["llm_attempts"]
    ] == [("Writer", 1, 1, "timeout", 61.0, True), ("Writer", 1, 2, "returned", 95.0, False)]
    assert saved["llm_attempts"][0]["error_type"] == "ConnectionError"
    # Units are labelled "<num>|<role>" so concurrent units in one process
    # could be told apart; the record carries the role alone.
    assert live.agents[3].llm._academic_agent_call_budget.stage == f"{num}|Writer"
    # The unit's observer does not outlive the unit.
    assert llm_config.set_attempt_observer(None) is None
