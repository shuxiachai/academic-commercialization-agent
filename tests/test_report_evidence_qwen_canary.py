"""Frozen synthetic controls, shared budget and actual core-to-HTTP transcripts."""

from decimal import Decimal
import hashlib
from importlib.metadata import PackageNotFoundError
import json
from types import SimpleNamespace
import tomllib

import pytest

import report_evidence_followup_canary as cli
import academic_agent.report_evidence_qwen_canary as canary
from academic_agent.report_evidence_qwen_transport import QwenFollowupTransport
from test_report_evidence_qwen_transport import (
    KEY, ledger as ledger, mock_http as mock_http, payload, request_kwargs, wire_response,
)


def native_read(source_id, call_id):
    return {"role": "assistant", "content": None, "tool_calls": [{
        "index": 0, "id": call_id, "type": "function", "function": {
            "name": "read_source", "arguments": json.dumps({"source_id": source_id, "offset": 0, "length": 1500}),
        },
    }]}


def scripted_provider(request):
    """The mock chooses a native tool; the application never unconditionally reads."""
    body = json.loads(request.content)
    is_market = "annual revenue" in body["messages"][1]["content"]
    source_id, call_id = ("M1", "native_m1") if is_market else ("A1", "native_a1")
    if body["messages"][-1]["role"] != "tool":
        return wire_response(payload(native_read(source_id, call_id)))
    message = body["messages"][-1]
    assert message["tool_call_id"] == call_id
    assert body["messages"][-2]["tool_calls"][0]["id"] == call_id
    assert "index" not in body["messages"][-2]["tool_calls"][0]
    result = json.loads(message["content"])
    if is_market:
        assert result["status"] == "missing_text" and result["source_id"] == "M1"
        final = {"answer": "The saved market text is unavailable; I abstain.", "status": "abstained", "evidence_ids": []}
    else:
        assert result["text"] == canary.load_cases()[0]["summary"]
        final = {"answer": "The test used 25 degrees Celsius; no field deployment was evaluated.",
                 "status": "answered", "evidence_ids": [result["evidence_id"]]}
    return wire_response(payload({"role": "assistant", "content": json.dumps(final)}))


def test_two_frozen_cases_cross_real_core_http_and_durable_ledger(tmp_path, mock_http):
    """Native replies must reach actual tool execution and the following HTTP body."""
    mock_http["handler"] = scripted_provider
    output = tmp_path / "successful"
    summary = canary.run_canary(api_key=KEY, output_dir=output, manifest={"mode": "offline_test"})
    assert summary["passed"] is True and summary["request_count"] == 4
    assert summary["unknown_usage_requests"] == 0 and not summary["unrun_cases"]
    assert summary["semantic_support"] == "not_assessed" and summary["answer_verification"] == "not_verified"
    events = [json.loads(line) for line in (output / "events.jsonl").read_text().splitlines()]
    assert [event["event"] for event in events] == ["request_reserved", "request_finished"] * 4
    assert [event["request_id"] for event in events] == [1, 1, 2, 2, 3, 3, 4, 4]
    assert all(event["provider_response_received"] for event in events if event["event"] == "request_finished")
    academic = json.loads((output / "FQ01.json").read_text())
    market = json.loads((output / "FQ02.json").read_text())
    assert academic["result"]["state"] == "answered_with_evidence"
    assert academic["result"]["evidence_ids"] == academic["result"]["audit"]["delivered_read_ids"]
    assert academic["narrow_content_control"] == "requires_parent_review"
    assert market["result"]["state"] == "abstained" and not market["result"]["served_evidence"]
    assert len(mock_http["requests"]) == 4 and KEY not in (output / "events.jsonl").read_text()
    assert set(path.name for path in output.iterdir()) == {"manifest.json", "events.jsonl", "FQ01.json", "FQ02.json", "summary.json"}


@pytest.mark.parametrize("defect", ["unknown_tool", "invalid_arguments"])
def test_local_tool_errors_stop_before_paid_repair_and_leave_second_case_unrun(tmp_path, mock_http, defect):
    """Phase-1 repair capability must not spend a second paid request in this canary."""
    message = native_read("A1", "invalid_native_request")
    function = message["tool_calls"][0]["function"]
    if defect == "unknown_tool":
        function["name"] = "fetch_url"
    else:
        function["arguments"] = '{"source_id":"A1","offset":true,"length":1500}'
    mock_http["handler"] = lambda request: wire_response(payload(message))
    output = tmp_path / defect
    summary = canary.run_canary(api_key=KEY, output_dir=output, manifest={"mode": "offline_test"})
    assert summary["passed"] is False and summary["stop_reason"] == "local_tool_error_no_repair"
    assert summary["request_count"] == len(mock_http["requests"]) == 1
    assert summary["unrun_cases"] == ["FQ02"]
    result = json.loads((output / "FQ01.json").read_text())["result"]
    assert result["state"] == "failed" and result["audit"]["transport_turns"] == 2
    assert result["audit"]["tool_errors"] == 1 and result["answer"] is None


def test_fq02_requires_actual_missing_m1_read_not_no_match_abstention(tmp_path, mock_http):
    """A no-match reply is not the pre-registered missing-text observation."""
    def respond(request):
        body = json.loads(request.content)
        if "annual revenue" not in body["messages"][1]["content"]:
            return scripted_provider(request)
        return wire_response(payload({"role": "assistant", "content": json.dumps({
            "answer": "No matches; I abstain.", "status": "abstained", "evidence_ids": [],
        })}))

    mock_http["handler"] = respond
    summary = canary.run_canary(api_key=KEY, output_dir=tmp_path / "missing_inspection", manifest={})
    assert summary["passed"] is False and summary["cases"][-1] == {"case_id": "FQ02", "passed": False}
    assert summary["stop_reason"] == "case_gate_failed"


def test_invalid_final_answer_keeps_usage_and_stops_remaining_case(tmp_path, mock_http):
    """Successful HTTP/usage parsing is not successful final-envelope validation."""
    mock_http["handler"] = lambda request: wire_response(payload({"role": "assistant", "content": "not JSON"}))
    output = tmp_path / "invalid_answer"
    summary = canary.run_canary(api_key=KEY, output_dir=output, manifest={})
    assert summary["passed"] is False and summary["stop_reason"] == "core_protocol_failed"
    assert summary["request_count"] == 1 and summary["unknown_usage_requests"] == 0
    assert Decimal(summary["known_usage_estimated_usd"]) > 0 and summary["unrun_cases"] == ["FQ02"]


def test_unknown_usage_stops_whole_batch_with_no_second_case(tmp_path, mock_http):
    """A missing usage response cannot be bypassed by opening the next synthetic case."""
    mock_http["handler"] = lambda request: wire_response(payload(usage=None))
    summary = canary.run_canary(api_key=KEY, output_dir=tmp_path / "unknown", manifest={})
    assert not summary["passed"] and summary["unknown_usage_requests"] == 1
    assert summary["unrun_cases"] == ["FQ02"] and len(mock_http["requests"]) == 1


def test_shared_six_request_limit_refuses_seventh_before_http(ledger, mock_http):
    """A case change cannot replenish the shared six-request allowance."""
    mock_http["handler"] = lambda request: wire_response(payload())
    transport = QwenFollowupTransport(KEY, ledger)
    for index in range(6):
        ledger.case_id = "FQ01" if index < 3 else "FQ02"
        transport(**request_kwargs())
    with pytest.raises(canary.CanaryStopped, match="request_limit"):
        transport(**request_kwargs())
    assert len(mock_http["requests"]) == ledger.summary()["request_count"] == 6
    assert Decimal(ledger.summary()["budget_consumed_usd"]) == canary.RESERVATION_USD * 6


def test_budget_reservation_refuses_dispatch_even_before_call_limit(ledger, mock_http, monkeypatch):
    """Reservation arithmetic must be checked before dispatch, not after a billed reply."""
    monkeypatch.setattr(canary, "USD_LIMIT", canary.RESERVATION_USD - Decimal("0.000000001"))
    with pytest.raises(canary.CanaryStopped, match="budget_limit"):
        QwenFollowupTransport(KEY, ledger)(**request_kwargs())
    assert not mock_http["requests"] and not ledger.records
    assert canary.RESERVATION_USD == (Decimal(16384) * Decimal("0.573") + Decimal(512) * Decimal("3.44")) / 1_000_000


def test_unresolved_intent_blocks_next_request_without_refund(ledger, mock_http):
    """A reserved request without finalization cannot be resumed or silently replaced."""
    ledger.reserve(request_kwargs())
    with pytest.raises(canary.CanaryStopped, match="unresolved_request"):
        QwenFollowupTransport(KEY, ledger)(**request_kwargs())
    assert ledger.pending == 1 and len(ledger.records) == 1 and not mock_http["requests"]
    assert ledger.summary()["cost_coverage"] == "lower_bound"


def test_occupied_output_is_preserved_without_any_dispatch(ledger, mock_http):
    """No force/resume/overwrite path may consume a previously occupied canary batch."""
    before = {path.name: path.read_bytes() for path in ledger.output_dir.iterdir()}
    with pytest.raises(canary.CanaryStopped, match="occupied"):
        canary.run_canary(api_key=KEY, output_dir=ledger.output_dir, manifest={})
    assert before == {path.name: path.read_bytes() for path in ledger.output_dir.iterdir()}
    assert not mock_http["requests"]


def test_case_results_are_write_once(ledger):
    """A second write cannot retrospectively replace a failure with a pass."""
    ledger.save("FQ01.json", {"passed": False})
    before = (ledger.output_dir / "FQ01.json").read_bytes()
    with pytest.raises(canary.CanaryStopped, match="persistence_failed"):
        ledger.save("FQ01.json", {"passed": True})
    assert (ledger.output_dir / "FQ01.json").read_bytes() == before


def test_frozen_fixture_matches_registered_bytes_and_cases():
    """The live runner can only open these fresh synthetic controls, never user reports."""
    cases = canary.load_cases()
    assert [case["case_id"] for case in cases] == ["FQ01", "FQ02"]
    assert cases[0]["summary"] == ("The synthetic sensor was tested only in a laboratory fixture at 25 degrees Celsius. "
                                    "No field deployment was evaluated.")
    assert cases[1]["source_id"] == "M1" and cases[1]["summary"] is None and cases[1]["origin"] == "unknown"
    assert hashlib.sha256((canary.ROOT / canary.FIXTURE).read_bytes()).hexdigest() == canary.FIXTURE_SHA256


@pytest.fixture
def identity_environment(monkeypatch):
    versions = {row["name"]: row["version"] for row in tomllib.loads((canary.ROOT / "uv.lock").read_text(encoding="utf-8"))["package"]}
    commands = []

    def git(args, **kwargs):
        commands.append(args)
        return SimpleNamespace(stdout="a" * 40 if args[1] == "rev-parse" else "")

    monkeypatch.setattr(canary.subprocess, "run", git)
    monkeypatch.setattr(canary, "version", versions.__getitem__)
    return commands, versions


def test_identity_binds_commit_fixture_source_lock_config_and_installed_versions(identity_environment):
    """Recording a version alone is insufficient: installed transport dependencies must match the lock."""
    commands, versions = identity_environment
    identity = canary.verify_identity("a" * 40)
    assert identity["commit"] == "a" * 40 and identity["fixture_sha256"] == canary.FIXTURE_SHA256
    assert set(identity["source_dependency_sha256"]) == set(canary.IDENTITY_PATHS)
    assert identity["runtime"]["httpx"] == versions["httpx"] == "0.28.1"
    assert identity["runtime"]["python-dotenv"] == versions["python-dotenv"]
    assert identity["configuration"] == canary.configuration()
    assert "pyproject.toml" in commands[1] and "uv.lock" in commands[1]
    project = tomllib.loads((canary.ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "httpx==0.28.1" in project["project"]["dependencies"]


@pytest.mark.parametrize("dependency", ["httpx", "pydantic", "httpcore", "anyio", "idna", "python-dotenv", "pydantic-core"])
def test_installed_direct_or_transitive_dependency_mismatch_refuses_identity(identity_environment, monkeypatch, dependency):
    """Direct and transitive installed drift must fail before a canary can be dispatched."""
    _, versions = identity_environment
    monkeypatch.setattr(canary, "version", lambda name: "0.0.0-mismatch" if name == dependency else versions[name])
    with pytest.raises(canary.CanaryStopped, match="installed_dependency_mismatch"):
        canary.verify_identity("a" * 40)


def test_missing_installed_dependency_is_safe_identity_failure(identity_environment, monkeypatch):
    """A missing distribution must not produce a traceback or a best-effort identity."""
    def missing(name):
        raise PackageNotFoundError("private metadata location")

    monkeypatch.setattr(canary, "version", missing)
    with pytest.raises(canary.CanaryStopped, match="identity_check_unavailable"):
        canary.verify_identity("a" * 40)


@pytest.mark.parametrize("defect", ["wrong_head", "dirty_source", "fixture_change"])
def test_identity_refuses_wrong_commit_dirty_source_and_fixture_drift(identity_environment, monkeypatch, defect):
    """The CLI cannot run on an uncommitted implementation or a changed synthetic control."""
    if defect == "fixture_change":
        monkeypatch.setattr(canary, "FIXTURE_SHA256", "0" * 64)
    else:
        monkeypatch.setattr(canary.subprocess, "run", lambda args, **kwargs: SimpleNamespace(
            stdout=("b" * 40 if defect == "wrong_head" else "a" * 40) if args[1] == "rev-parse" else
            (" M src/academic_agent/report_evidence_qwen_transport.py" if defect == "dirty_source" else "")))
    with pytest.raises(canary.CanaryStopped):
        canary.verify_identity("a" * 40)


@pytest.mark.parametrize("use_dotenv", [False, True])
def test_cli_uses_only_dedicated_key_without_changing_global_environment(tmp_path, monkeypatch, capsys, use_dotenv):
    """A mismatched global provider/model/base and legacy key cannot redirect the canary."""
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "verify_identity", lambda commit: {"commit": commit})
    monkeypatch.setenv("DASHSCOPE_API_KEY", KEY)
    monkeypatch.setenv("OPENAI_API_KEY", "other-private-key")
    monkeypatch.setenv("LLM_PROVIDER", "not-qwen")
    monkeypatch.setenv("QWEN_MODEL", "other-model")
    seen = []

    def run(**kwargs):
        seen.append(kwargs)
        return {"passed": True}

    monkeypatch.setattr(cli, "run_canary", run)
    args = ["--expected-commit", "a" * 40, "--output-dir", str(tmp_path / "outputs" / "new")]
    if use_dotenv:
        import dotenv

        def read(path, **kwargs):
            assert path == tmp_path / ".env" and kwargs == {"interpolate": False}
            return {"DASHSCOPE_API_KEY": KEY, "OPENAI_API_KEY": "must-not-use"}

        monkeypatch.setattr(dotenv, "dotenv_values", read)
        args.append("--key-from-dotenv")
    assert cli.main(args) == 0
    assert seen[0]["api_key"] == KEY and cli.os.environ["LLM_PROVIDER"] == "not-qwen"
    assert cli.os.environ["QWEN_MODEL"] == "other-model"
    assert KEY not in capsys.readouterr().out


def test_cli_missing_dedicated_key_never_uses_legacy_key(tmp_path, monkeypatch, capsys):
    """An ambient OpenAI key is not authorization to bill this Qwen canary."""
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "verify_identity", lambda commit: {})
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "private-legacy-key")
    monkeypatch.setattr(cli, "run_canary", lambda **kwargs: pytest.fail("legacy fallback dispatched"))
    assert cli.main(["--expected-commit", "a" * 40, "--output-dir", str(tmp_path / "outputs" / "new")]) == 1
    output = capsys.readouterr().out
    assert "invalid_dedicated_key" in output and "private-legacy-key" not in output


def test_cli_rejects_force_resume_or_credentials_without_echoing_values(capsys):
    """An unsupported credential flag must not print its secret through argparse."""
    with pytest.raises(SystemExit) as exc:
        cli.main(["--expected-commit", "a" * 40, "--output-dir", "outputs/new", "--api-key", KEY, "--force", "--resume"])
    assert exc.value.code == 2
    assert KEY not in capsys.readouterr().err
