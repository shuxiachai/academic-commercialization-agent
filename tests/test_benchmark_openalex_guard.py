"""A benchmark run does not score evidence that OpenAlex refused to provide.

On 2026-10-19 the anonymous OpenAlex budget ran out mid-batch: the last five
held-out v2 runs and both hyperloop confirmation runs were scored with no
OpenAlex evidence, and nothing said so. Only the Crew's paid execution and
live retrieval are replaced here; batch acceptance and run_topic are real.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import benchmark
import benchmark_fixtures
import benchmark_identity as identity
from academic_agent import crew, llm_config, source_pipeline
from academic_agent.source_clients import OPENALEX_RATE_LIMITED, S2_RATE_LIMITED
from academic_agent.source_pipeline import SearchAudit


def _collection(*notes: str):
    """A frozen collection with these notes added to its OA-Cited audit row."""
    num, topic, *_ = benchmark.TOPICS[0]
    collection = benchmark_fixtures.load(num, benchmark._slug(topic))
    collection.audit.append(SearchAudit(domain="academic", query=f"[OA-Cited] {topic}",
                                        result_count=0, rejected_reasons=list(notes)))
    return collection


@pytest.fixture
def live(tmp_path, monkeypatch):
    monkeypatch.setattr(identity, "BATCH_ROOT", tmp_path / "batches")
    config = SimpleNamespace(provider="qwen", model="qwen3.5-plus", base_url="https://example.test/v1", api_key="unused")
    monkeypatch.setattr(llm_config, "resolve_provider_config", lambda: config)
    kickoff = Mock(return_value=SimpleNamespace(tasks_output=[], raw="unused"))
    monkeypatch.setattr(crew, "AcademicAgent", lambda _: SimpleNamespace(crew=lambda: SimpleNamespace(kickoff=kickoff, agents=[])))
    selected = [(*benchmark.TOPICS[0], 1), (*benchmark.TOPICS[0], 2)]
    batch = identity.prepare_batch(selected, False, experiment_id="openalex-guard")
    return SimpleNamespace(selected=selected, batch=batch, kickoff=kickoff, monkeypatch=monkeypatch)


def test_refusal_and_failure_notes_are_recognised():
    audit = [SimpleNamespace(rejected_reasons=[
        OPENALEX_RATE_LIMITED, "OpenAlex request failed (HTTP 503)", S2_RATE_LIMITED,
        "OpenAlex title not relevant to topic: 'Why the request failed'",
    ])]
    assert benchmark._openalex_refusals(audit) == sorted([OPENALEX_RATE_LIMITED, "OpenAlex request failed (HTTP 503)"])


def test_a_refused_run_is_recorded_and_never_scored(live):
    live.monkeypatch.setattr(source_pipeline, "collect_source_collection", lambda topic: _collection(OPENALEX_RATE_LIMITED))
    num, topic, trl, industry, rep = live.selected[0]
    meta = benchmark.run_topic(num, topic, trl, industry, rep=rep, batch=live.batch)
    assert meta["status"] == "error_retrieval_refused"
    assert meta["retrieval_refusals"] == [OPENALEX_RATE_LIMITED]
    assert live.kickoff.call_count == 0
    saved = json.loads((Path(meta["run_dir"]) / "meta.json").read_text(encoding="utf-8"))
    assert saved["status"] == "error_retrieval_refused"


def test_the_serial_batch_stops_at_the_first_refusal(live):
    live.monkeypatch.setattr(source_pipeline, "collect_source_collection", lambda topic: _collection(OPENALEX_RATE_LIMITED))
    results = benchmark._run_serial(live.selected, dry_run=False, batch=live.batch)
    assert [r["status"] for r in results] == ["error_retrieval_refused"]
    second = benchmark._run_dir(*live.selected[1][:2], live.selected[1][4], root=Path(live.batch["root"]))
    assert not second.exists()


def test_a_semantic_scholar_refusal_alone_still_runs(live):
    live.monkeypatch.setattr(source_pipeline, "collect_source_collection", lambda topic: _collection(S2_RATE_LIMITED))
    num, topic, trl, industry, rep = live.selected[0]
    benchmark.run_topic(num, topic, trl, industry, rep=rep, batch=live.batch)
    assert live.kickoff.call_count == 1


def test_a_live_batch_needs_a_key_or_an_explicit_waiver(monkeypatch, capsys):
    import dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", ["benchmark.py", "--only", benchmark.TOPICS[0][0]])
    with pytest.raises(SystemExit):
        benchmark.main()
    assert "OPENALEX_API_KEY is not set" in capsys.readouterr().err
    monkeypatch.setattr(sys, "argv", ["benchmark.py", "--only", benchmark.TOPICS[0][0], "--dry-run"])
    benchmark.main()  # simulated work needs no key
