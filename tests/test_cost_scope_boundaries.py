"""Pricing failures and scope must survive collector -> files -> HTTP -> JS.

All metrics are synthetic. No provider client or real credential is used.
The API fixture writes a completed report to an isolated temporary directory.
"""

import json
import math
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from academic_agent import token_usage
from api import access, runs
from api.main import app


def crew(count=1, model="qwen3.5-plus"):
    metrics = SimpleNamespace(prompt_tokens=100, completion_tokens=50,
                              total_tokens=150, successful_requests=1)
    return SimpleNamespace(agents=[SimpleNamespace(role=f"Node {i}", llm=SimpleNamespace(
        model=model, get_token_usage_summary=lambda: metrics)) for i in range(count)])


@pytest.mark.parametrize("raw", ["nan:1", "NaN:2:1", "1:inf", "1:2:-inf", "1e309:1", "-1:2", "bad"])
def test_invalid_rate_override_is_finite_visible_fallback(monkeypatch, raw):
    """Malformed operator rates cannot produce NaN marked as a complete bill."""
    monkeypatch.setenv("LLM_PRICE_PER_MTOK", raw)
    result = token_usage.collect_usage(crew()).as_dict()
    assert result["cost_usd"] is not None
    assert math.isfinite(result["cost_usd"])
    assert result["cost_complete"] is False
    assert result["pricing_warnings"] == ["invalid_price_override"]
    assert "built-in" in result["price_basis"]
    assert raw not in result["pricing_warnings"]
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("rate", ["1e308:1e308", "1e307:1e307"])
def test_finite_rate_arithmetic_overflow_is_unknown_not_free(monkeypatch, rate):
    """Finite input validation alone does not make multiplication finite."""
    monkeypatch.setenv("LLM_PRICE_PER_MTOK", rate)
    result = token_usage.collect_usage(crew()).as_dict()
    assert result["cost_usd"] is None
    assert result["cost_complete"] is False
    assert result["total_tokens"] == 150
    json.dumps(result, allow_nan=False)


def test_sum_overflow_is_unknown_and_no_nonstandard_json(monkeypatch):
    """Each node can be finite while the total overflows."""
    monkeypatch.setenv("LLM_PRICE_PER_MTOK", "")
    monkeypatch.setattr(token_usage, "cost_for", lambda *a, **kw: 1e308)
    result = token_usage.collect_usage(crew(2)).as_dict()
    assert result["cost_usd"] is None
    assert result["cost_complete"] is False
    assert "nonfinite_total" in result["pricing_warnings"]
    json.dumps(result, allow_nan=False)


def test_no_known_prices_and_no_reporters_are_not_zero_or_complete(monkeypatch):
    """Silence is not evidence of free execution."""
    monkeypatch.setenv("LLM_PRICE_PER_MTOK", "")
    for candidate in (crew(model="unpriced-new-model"), SimpleNamespace(agents=[]),
                      SimpleNamespace(agents=[SimpleNamespace(llm=object())])):
        result = token_usage.collect_usage(candidate).as_dict()
        assert result["cost_usd"] is None
        assert result["cost_complete"] is False
        assert result["end_to_end_cost_complete"] is False


@pytest.mark.parametrize("terminal", [False, True])
def test_scope_reaches_both_http_endpoints_from_actual_collector(tmp_path, monkeypatch, terminal):
    """A dict stored correctly but silently dropped at delivery is still broken."""
    from datetime import UTC, datetime, timedelta
    from academic_agent.run_terminal import TerminalRecord, UsageAccounting, commit_terminal_record
    from academic_agent.pipeline_worker import _merge_usage_snapshots

    monkeypatch.setenv("LLM_PRICE_PER_MTOK", "")
    monkeypatch.setattr(runs, "DEFAULT_OUTPUT_ROOT", tmp_path)
    monkeypatch.setattr(runs, "_registry", {})
    monkeypatch.setattr(access, "ACCESS_CODE", None)
    monkeypatch.setattr(access, "ACCESS_CODES", None)
    rid = "20260910T010000Z-aaaaaaaaaa"
    directory = tmp_path / rid
    directory.mkdir()
    usage = _merge_usage_snapshots(token_usage.collect_usage(crew()).as_dict(),
                                   token_usage.collect_usage(crew()).as_dict())
    (directory / "status.json").write_text(json.dumps({"done": True, "stage": "Done", "usage": usage}), encoding="utf-8")
    (directory / "commercialization_report.md").write_text("# Preserved report", encoding="utf-8")
    if terminal:
        start = datetime(2026, 9, 10, tzinfo=UTC)
        commit_terminal_record(directory, TerminalRecord(
            state="completed", reason_code="worker_completed", termination_method="worker_exit",
            started_at=start, ended_at=start + timedelta(seconds=7), elapsed_seconds=7,
            usage=usage, usage_accounting=UsageAccounting(state="complete", snapshot_at=start,
                run_complete=True, in_flight_request_may_have_spent=False)))
    client = TestClient(app, raise_server_exceptions=False)
    for suffix in ("", "/progress"):
        response = client.get(f"/api/runs/{rid}{suffix}")
        assert response.status_code == 200
        assert response.json()["usage"] == usage
        assert response.json()["usage"].get("accounting_scope") == "crew_nodes"
        assert response.json()["usage"]["end_to_end_cost_complete"] is False
        assert "pdf_extraction" in response.json()["usage"]["excluded_stages"]
