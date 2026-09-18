"""Fixed RF runner through real RP, reader and HTTP; fake git blobs/keys only."""

from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import textwrap
import tomllib
from types import SimpleNamespace

import httpx
import pytest

from academic_agent import report_evidence_read_first_canary as runner
from test_report_evidence_read_first_qwen_transport import KEY, USAGE, final, payload, policy_expansion_snapshot, read

REAL_ROOT = runner.ROOT
COMMIT = "a" * 40


@pytest.fixture
def batch(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    blobs = {}
    for name in runner.IDENTITY_PATHS:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REAL_ROOT / name, path)
        blobs[name] = path.read_bytes().replace(b"\r\n", b"\n")
    (repo / "outputs").mkdir()
    versions = {row["name"]: row["version"] for row in tomllib.loads(
        (repo / "uv.lock").read_text(encoding="utf-8"))["package"]}
    state = SimpleNamespace(repo=repo, blobs=blobs, versions=versions, requests=[], reads=[], key_reads=[],
                            change=None, wrong_label=False, git_calls=[], output=repo / runner.FIXED_OUTPUT)

    def git(*args):
        state.git_calls.append(args)
        if args[0] == "rev-parse":
            return COMMIT.encode() + b"\n"
        if args[0] == "status":
            return b""
        assert args[0] == "show" and args[1].startswith(COMMIT + ":")
        return blobs[args[1].split(":", 1)[1]]

    class Environment:
        def get(self, name):
            state.key_reads.append(name)
            assert name == "DASHSCOPE_API_KEY"
            return KEY

    class OS:
        environ = Environment()

        def __getattr__(self, name):
            return getattr(os, name)

    monkeypatch.setattr(runner, "ROOT", repo)
    monkeypatch.setattr(runner, "_git", git)
    monkeypatch.setattr(runner, "version", versions.__getitem__)
    monkeypatch.setattr(runner, "os", OS())
    real_client, real_read = httpx.AsyncClient, runner.core.read_source

    def dispatch(request):
        state.requests.append(request)
        body = json.loads(request.content)
        if body.get("tools"):
            message = read()
        else:
            case = next(case for case in runner.load_cases() if case["claim"] == body["messages"][1]["content"])
            message = final(body, "supported" if state.wrong_label else case["expected_relation"])
        reply = payload(message)
        if state.change:
            state.change(reply, body)
        return httpx.Response(200, stream=httpx.ByteStream(runner._encoded(reply)))

    def client(**kwargs):
        assert isinstance(kwargs["transport"], httpx.MockTransport)
        assert kwargs["trust_env"] is False
        return real_client(**kwargs)

    def observed_read(*args, **kwargs):
        state.reads.append((args, kwargs))
        return real_read(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", lambda **kwargs: httpx.MockTransport(dispatch))
    monkeypatch.setattr(httpx, "AsyncClient", client)
    monkeypatch.setattr(runner.core, "read_source", observed_read)
    return state


def run():
    return runner.run_canary(expected_commit=COMMIT, expected_fixture_sha256=runner.FIXTURE_SHA256,
                             authorize_paid=runner.PROTOCOL_IDENTITY)


def saved(path):
    return json.loads(path.read_text(encoding="utf-8"))


def events(batch):
    return [json.loads(line) for line in (batch.output / "events.jsonl").read_text(encoding="utf-8").splitlines()]


def test_six_actual_requests_frozen_references_and_separate_audits(batch):
    """Success requires actual full reads, forced wire choice and both audits."""
    result = run()
    assert result["batch_passed"] is True and result["summary_persisted"] is True
    assert result["label_checks"] == result["label_matches"] == result["mechanically_passed_cases"] == 3
    assert result["unrun_cases"] == [] and result["request_count"] == 6
    assert len(batch.requests) == 6 and len(batch.reads) == 3
    assert batch.key_reads == ["DASHSCOPE_API_KEY"]
    assert saved(batch.output / "summary.json") == result
    assert saved(batch.output / "manifest.json")["live_authorization"] is False
    records = events(batch)
    intents = [row for row in records if row["event"] == "request_reserved"]
    callbacks = [row for row in records if row["event"] == "read_first_callback"]
    assert len(intents) == len(callbacks) == 6
    for i, (request, intent, entry) in enumerate(zip(batch.requests, intents, callbacks, strict=True)):
        assert request.content == runner._encoded(intent["request"])
        assert entry["native_body_hash"] == intent["request_sha256"] == runner.native.digest(request.content)
        assert entry["request_hash"] == runner.native.digest(runner._encoded(entry["request"]))
        body = json.loads(request.content)
        assert body["tool_choice"] == ("none" if i % 2 else runner.native.NAMED_CHOICE)
        assert entry["tool_choice"] == ("none" if i % 2 else "auto")
        for forbidden in ("reference_status", "expected_relation", "proposition_kind", "reference_rationale"):
            assert forbidden.encode() not in request.content
    for index, case in enumerate(runner.load_cases()):
        result = saved(batch.output / (case["case_id"] + ".json"))
        assert result["mechanical_passed"] and result["label_match_passed"]
        assert result["availability"]["policy_callback_delivery"]["state"] == "usable_text"
        assert result["availability"]["read_executions"] == 1
        assert [row["request_id"] for row in result["availability"]["native_intent_response"]["requests"]] == [
            2 * index + 1, 2 * index + 2]
        assert result["message_representation"] == "projected_native_assistant_message_not_raw_http"
    # One initial plus two per request (before/after) identity validations.
    assert sum(args[0] == "rev-parse" for args in batch.git_calls) == 13


@pytest.mark.parametrize("fault", ["early_final", "partial_read", "refusal", "wrong_label", "model", "usage"])
def test_first_failure_stops_and_preserves_separate_outcomes(batch, fault):
    def change(reply, body):
        if body.get("tools"):
            if fault == "early_final":
                reply["choices"][0] = {"index": 0, "finish_reason": "stop", "message": final(body, "unavailable")}
            elif fault == "partial_read":
                reply["choices"][0]["message"] = read(length=1)
            elif fault == "refusal":
                reply["choices"][0] = {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "refusal": "No"}}
            elif fault == "model":
                reply["model"] = "other"
            elif fault == "usage":
                reply["usage"]["prompt_tokens"] = True
    batch.change, batch.wrong_label = change, fault == "wrong_label"
    result = run()
    assert result["batch_passed"] is False and result["unrun_cases"] == ["RF02", "RF03"]
    assert result["request_count"] == (2 if fault == "wrong_label" else 1)
    assert len(batch.reads) == int(fault == "wrong_label")
    case = result["cases"][0]
    assert case["mechanical_passed"] is (fault == "wrong_label")
    assert case["label_match_passed"] is (False if fault == "wrong_label" else None)
    if fault == "early_final":
        assert result["stop_reason"] == "full_native_read_required"
        assert saved(batch.output / "RF01.json")["result"]["inner"]["state"] == "failed"
        assert result["semantic_review"] == "not_reviewable" and result["label_checks"] == 0
    assert result["unknown_usage_requests"] == int(fault == "usage")


@pytest.mark.parametrize("fault", ["rp_hash", "raw_bool", "original_choice", "native_choice", "result_text", "receipt"])
def test_audit_forgery_cannot_buy_next_case(batch, monkeypatch, fault):
    original = runner._case_gate

    def gate(case, snapshot, result, transport, first):
        if fault == "rp_hash":
            entry = result.audit.callback_entries[0].model_copy(update={"request_hash": "0" * 64})
            result = result.model_copy(update={"audit": result.audit.model_copy(
                update={"callback_entries": (entry, *result.audit.callback_entries[1:])})})
        elif fault == "raw_bool":
            object.__setattr__(result.inner.audit.catalog.core, "tool_executions", True)
        elif fault == "receipt":
            result = result.model_copy(update={"inner": result.inner.model_copy(
                update={"served_evidence": ()})})
        else:
            if fault == "original_choice":
                transport.exchanges[0]["request"]["tool_choice"] = deepcopy(runner.native.NAMED_CHOICE)
            elif fault == "native_choice":
                transport.ledger.records[first]["request"]["tool_choice"] = "auto"
            else:
                message = transport.exchanges[1]["request"]["messages"][-1]
                value = json.loads(message["content"])
                value["text"] = "Forged text with unchanged receipt."
                message["content"] = json.dumps(value)
        return original(case, snapshot, result, transport, first)
    monkeypatch.setattr(runner, "_case_gate", gate)
    result = run()
    assert not result["batch_passed"] and result["unrun_cases"] == ["RF02", "RF03"]
    assert len(batch.requests) == 2 and not result["cases"][0]["mechanical_passed"]


@pytest.mark.parametrize("phase", ["before", "after", "after_error"])
def test_exact_identity_each_call_including_rejected_reply(batch, monkeypatch, phase):
    original = runner.verify_identity
    calls, order, finished_at_post = [], [], []

    def verify(*args):
        calls.append(args)
        order.append(("identity", len(calls)))
        if len(calls) == 3:
            finished_at_post.extend(row for row in events(batch) if row["event"] == "request_finished")
        if len(calls) == (2 if phase == "before" else 3):
            raise runner.CanaryStopped("runtime_identity_changed")
        return original(*args)
    monkeypatch.setattr(runner, "verify_identity", verify)

    def reply_observed(reply, body):
        order.append(("http_reply", len(batch.requests)))
        if phase == "after_error":
            reply["model"] = "other"
    batch.change = reply_observed
    result = run()
    assert calls == [(COMMIT, runner.FIXTURE_SHA256)] * (2 if phase == "before" else 3)
    assert order == [("identity", 1), ("identity", 2)] + (
        [] if phase == "before" else [("http_reply", 1), ("identity", 3)])
    assert not result["batch_passed"] and result["unrun_cases"] == ["RF02", "RF03"]
    assert len(batch.requests) == int(phase != "before") and not batch.reads
    if phase != "before":
        assert len(finished_at_post) == 1
        assert finished_at_post[0]["reported_usage"] == USAGE and result["unknown_usage_requests"] == 0
        assert finished_at_post[0]["error"] == ("unexpected_response_model" if phase == "after_error" else None)


@pytest.mark.parametrize("boundary", ["policy_budget", "reserved_only", "response_rejected"])
def test_failed_case_availability_preserves_each_delivery_boundary(batch, monkeypatch, boundary):
    """Real RP expansion and reserved-but-unsent bodies must not become delivery."""
    if boundary == "policy_budget":
        original = runner.snapshot_for
        monkeypatch.setattr(runner, "snapshot_for", lambda case: policy_expansion_snapshot(original(case), case["claim"]))
    elif boundary == "reserved_only":
        original_append = runner.native.ReadFirstQwenLedger._append

        def reject_dispatch(ledger, event):
            if event["event"] == "read_first_callback" and event["native_ordinal"] == 2:
                ledger.stop_reason = "persistence_failed"
                raise runner.CanaryStopped("persistence_failed")
            original_append(ledger, event)
        monkeypatch.setattr(runner.native.ReadFirstQwenLedger, "_append", reject_dispatch)
    else:
        def reject_response(reply, body):
            if body["messages"][-1]["role"] == "tool":
                reply["model"] = "other"
        batch.change = reject_response
    summary = run()
    assert summary["batch_passed"] is False and summary["unrun_cases"] == ["RF02", "RF03"]
    assert len(batch.reads) == 1 and len(batch.requests) == (2 if boundary == "response_rejected" else 1)
    case = saved(batch.output / "RF01.json")
    availability, observation = case["availability"], case["result"]
    assert availability == summary["cases"][0]["availability"] == saved(batch.output / "summary.json")["cases"][0]["availability"]
    assert availability["read_executions"] == 1 and "state" not in availability
    inner, callback = availability["inner_delivery"], availability["policy_callback_delivery"]
    assert inner["scope"] == "inner_to_relation_policy" and inner["state"] == "usable_text"
    assert len(inner["delivered_read_ids"]) == len(inner["usable_read_ids"]) == 1
    assert callback["scope"] == "relation_policy_to_callback"
    if boundary == "policy_budget":
        assert observation["inner"]["audit"]["callback_bytes"][-1] <= runner.policy.MAX_CALLBACK_BYTES
        assert observation["audit"]["blocked_callback_bytes"] > runner.policy.MAX_CALLBACK_BYTES
        assert observation["audit"]["blocked_reason"] == "callback_budget_exceeded"
        assert callback["callback_count"] == 1 and callback["blocked_reason"] == "callback_budget_exceeded"
        assert callback["delivered_read_ids"] == callback["usable_read_ids"] == []
        assert callback["state"] == "read_result_not_delivered" and callback["read_result_reason"] is None
    else:
        assert callback["callback_count"] == 2 and callback["blocked_reason"] is None
        assert callback["delivered_read_ids"] == callback["usable_read_ids"] == inner["delivered_read_ids"]
    native = availability["native_intent_response"]
    assert native["scope"] == "reservation_and_observed_response_only"
    assert native["provider_evidence_receipt"] == "not_attested"
    assert len(native["requests"]) == (1 if boundary == "policy_budget" else 2)
    assert native["requests"][0]["reserved_body_receipt_ids"] == []
    assert native["requests"][0]["provider_response_received"] is True
    if boundary != "policy_budget":
        second = native["requests"][1]
        assert second["reserved_body_receipt_ids"] == second["reserved_body_usable_receipt_ids"] == inner["delivered_read_ids"]
        assert second["provider_response_received"] is (boundary == "response_rejected")
        assert second["native_protocol_accepted"] is False
        assert second["usage_status"] == ("unknown" if boundary == "reserved_only" else "complete")
    assert summary["unknown_usage_requests"] == int(boundary == "reserved_only")


@pytest.mark.parametrize("fault", ["fixture", "blob", "version", "reparse", "occupied"])
def test_identity_and_occupied_preflight_before_credentials(batch, monkeypatch, fault):
    if fault == "fixture":
        path = batch.repo / runner.FIXTURE
        path.write_bytes(path.read_bytes() + b"\n")
    elif fault == "blob":
        batch.blobs["src/academic_agent/report_evidence_read_first_qwen_transport.py"] += b"\n"
    elif fault == "version":
        batch.versions["httpx"] = "0.0.0"
    elif fault == "reparse":
        original = Path.lstat

        def lstat(path, *args, **kwargs):
            if path == batch.repo:
                return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
            return original(path, *args, **kwargs)
        monkeypatch.setattr(Path, "lstat", lstat)
    else:
        batch.output.mkdir()
        (batch.output / "partial").write_text("occupied")
    with pytest.raises(runner.CanaryStopped):
        run()
    assert not batch.key_reads and not batch.requests and not batch.reads
    if fault == "occupied":
        assert (batch.output / "partial").read_text() == "occupied"


@pytest.mark.parametrize("target", ["identity.json", "RF01.json", "summary.json"])
def test_publication_failure_cannot_publish_success_or_buy_next_case(batch, monkeypatch, target):
    real_link = os.link

    def link(source, destination):
        if Path(destination).name == target:
            raise OSError("scripted publication failure")
        return real_link(source, destination)
    monkeypatch.setattr(runner.os, "link", link)
    if target == "identity.json":
        with pytest.raises(runner.CanaryStopped, match="persistence_failed"):
            run()
        assert not batch.requests
    else:
        result = run()
        assert not result["batch_passed"]
        assert len(batch.requests) == (2 if target == "RF01.json" else 6)
        assert result["stop_reason"] == "persistence_failed"
        if target == "summary.json":
            assert result["summary_persisted"] is False
    assert not (batch.output / target).exists()
    assert (batch.output / ("." + target + ".pending")).exists()


def test_default_cli_identity_only_and_invalid_arguments_are_safe(batch, capsys):
    args = ["--expected-commit", COMMIT, "--expected-fixture-sha256", runner.FIXTURE_SHA256]
    assert runner.main(args) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["mode"] == "identity_only" and output["live_authorized"] is False
    assert not batch.key_reads and not batch.requests and not batch.output.exists()
    with pytest.raises(SystemExit) as error:
        runner.main([*args, "--unknown", KEY])
    assert error.value.code == 2 and KEY not in capsys.readouterr().err
    assert runner.main([*args, "--authorize-paid", "old_protocol"]) == 1
    assert not batch.key_reads and not batch.output.exists()


def test_default_cli_fresh_process_guards_import_and_identity_path(batch):
    """Fresh import/main with empty credential environment; git/version are fixtures.

    This adds process-local isolation evidence, not a claim that an uncommitted
    candidate passed real committed-source admission or has a hard sandbox.
    """
    script = textwrap.dedent(r'''
        import os
        from pathlib import Path
        import sys
        import tomllib

        class EmptyEnvironment(dict):
            def check(self, name):
                if any(part in name.upper() for part in ("KEY", "TOKEN", "SECRET", "PASSWORD")):
                    raise AssertionError("credential lookup forbidden")
            def get(self, name, default=None):
                self.check(name)
                return super().get(name, default)
            def __getitem__(self, name):
                self.check(name)
                return super().__getitem__(name)
            def __iter__(self):
                raise AssertionError("environment enumeration forbidden")
            def items(self):
                raise AssertionError("environment enumeration forbidden")

        os.environ = EmptyEnvironment()
        def guard(event, args):
            if event.startswith("socket.") or event == "subprocess.Popen":
                raise AssertionError("native dispatch forbidden")
            if event == "open":
                path, mode, flags = args
                if isinstance(path, (str, bytes)) and Path(os.fsdecode(path)).name in {".env", "auth.json", "credentials.json"}:
                    raise AssertionError("credential file forbidden")
                if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
                    raise AssertionError("identity-only writes forbidden")
        sys.addaudithook(guard)
        from academic_agent import report_evidence_read_first_canary as candidate
        candidate.ROOT = Path(sys.argv[1])
        commit, fixture_hash = sys.argv[2:]
        def git(*args):
            if args[0] == "rev-parse":
                return commit.encode() + b"\n"
            if args[0] == "status":
                return b""
            assert args[0] == "show" and args[1].startswith(commit + ":")
            return (candidate.ROOT / args[1].split(":", 1)[1]).read_bytes().replace(b"\r\n", b"\n")
        candidate._git = git
        versions = {row["name"]: row["version"] for row in tomllib.loads(
            (candidate.ROOT / "uv.lock").read_text(encoding="utf-8"))["package"]}
        candidate.version = versions.__getitem__
        raise SystemExit(candidate.main(["--expected-commit", commit, "--expected-fixture-sha256", fixture_hash]))
    ''')
    environment = {"PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    if os.name == "nt":
        environment["SystemRoot"] = os.environ.get("SystemRoot", r"C:\Windows")
    completed = subprocess.run([sys.executable, "-c", script, str(batch.repo), COMMIT, runner.FIXTURE_SHA256],
                               cwd=REAL_ROOT, env=environment, capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert json.loads(completed.stdout)["mode"] == "identity_only"
    assert not batch.output.exists() and not batch.requests and not batch.key_reads


def test_dependency_closure_and_frozen_preparation_identity(batch):
    """Runner identity includes imports reached by the reused pure helpers."""
    assert runner.FIXTURE_SHA256 == runner.native.digest((REAL_ROOT / runner.FIXTURE).read_bytes())
    assert {case["case_id"] for case in runner.load_cases()} == {"RF01", "RF02", "RF03"}
    assert "src/academic_agent/report_evidence_stage_qwen_transport.py" in runner.IDENTITY_PATHS
    assert not any("relation_policy_qwen_canary" in path for path in runner.IDENTITY_PATHS)
    identity = runner.verify_identity(COMMIT, runner.FIXTURE_SHA256)
    assert set(identity["disk_sha256"]) == set(runner.IDENTITY_PATHS)
