"""SLQ through the actual locator/adapter/HTTP primitive, with fake credentials.

Git blobs and installed-version observations are fixture inputs; these tests do
not attest a real committed live identity, provider compatibility or selection.
"""

from copy import deepcopy
from decimal import Decimal
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

from academic_agent import report_evidence_qwen_canary as base
from academic_agent import report_evidence_source_locator_canary as runner

REAL_ROOT = runner.ROOT
COMMIT = "a" * 40
KEY = "sk-slq-fake-key-never-live"
USAGE = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}


def selection(source_id):
    if source_id is None:
        return {"role": "assistant", "content": '{"action":"decline"}'}
    return {"role": "assistant", "content": None, "tool_calls": [{
        "id": "fake_slq_call", "type": "function",
        "function": {"name": "read_source", "arguments": json.dumps({"source_id": source_id})},
    }]}


def saved(path):
    return json.loads(path.read_text(encoding="utf-8"))


def run():
    return runner.run_canary(expected_commit=COMMIT, expected_fixture_sha256=runner.FIXTURE_SHA256,
                             authorize_paid=runner.PROTOCOL_IDENTITY)


class _OS:
    def __getattr__(self, name):
        return getattr(os, name)


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
    state = SimpleNamespace(repo=repo, blobs=blobs, versions=versions, output=repo / runner.FIXED_OUTPUT,
                            requests=[], reads=[], key_reads=[], change=None, before_http=None,
                            intents=[], fsynced=[], options=[], transport_options=[], ledgers=[])

    def git(*args):
        if args[0] == "rev-parse":
            return COMMIT.encode() + b"\n"
        if args[0] == "status":
            return b""
        assert args[0] == "show" and args[1].startswith(COMMIT + ":")
        return blobs[args[1].split(":", 1)[1]]

    def fake_key(name):
        state.key_reads.append(name)
        assert name == "DASHSCOPE_API_KEY"
        return KEY

    local_os = _OS()
    local_os.environ = SimpleNamespace(get=fake_key)
    monkeypatch.setattr(runner, "os", local_os)
    monkeypatch.setattr(runner, "ROOT", repo)
    monkeypatch.setattr(runner, "_git", git)
    monkeypatch.setattr(runner, "version", versions.__getitem__)
    real_client, real_read = httpx.AsyncClient, runner.locator.read_source
    real_init = runner.native.LocatorQwenLedger.__init__

    def ledger_init(self, *args, **kwargs):
        real_init(self, *args, **kwargs)
        state.ledgers.append(self)

    monkeypatch.setattr(runner.native.LocatorQwenLedger, "__init__", ledger_init)
    base_os = _OS()

    def synced(fd):
        os.fsync(fd)
        state.fsynced.append({str(path): path.read_bytes() for path in state.output.glob("*/events.jsonl")})

    base_os.fsync = synced
    monkeypatch.setattr(base, "os", base_os)

    def dispatch(request):
        state.requests.append(request)
        body = json.loads(request.content)
        case = next(case for case in runner.load_cases() if case["question"] == body["messages"][1]["content"])
        journal = state.output / case["case_id"] / "events.jsonl"
        state.intents.append((journal.read_bytes(), deepcopy(state.fsynced)))
        if state.before_http:
            state.before_http()
        message = selection(case["expected_source_id"])
        reply = {"model": "qwen3.5-plus", "usage": dict(USAGE), "choices": [{
            "index": 0, "message": message, "finish_reason": "tool_calls" if message.get("tool_calls") else "stop",
        }]}
        if state.change:
            state.change(reply, case)
        return httpx.Response(200, stream=httpx.ByteStream(runner._encoded(reply)))

    def transport(**kwargs):
        state.transport_options.append(kwargs)
        return httpx.MockTransport(dispatch)

    def client(**kwargs):
        assert isinstance(kwargs["transport"], httpx.MockTransport)
        state.options.append(kwargs)
        return real_client(**kwargs)

    def observed_read(*args, **kwargs):
        state.reads.append((args, kwargs))
        return real_read(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", transport)
    monkeypatch.setattr(httpx, "AsyncClient", client)
    monkeypatch.setattr(runner.locator, "read_source", observed_read)
    return state


def test_four_actual_http_requests_independent_ledgers_and_local_json(batch):
    """The success denominator requires wire, durable intents, real reads and four publications."""
    result = run()
    assert result["batch_passed"] and result["summary_persisted"]
    assert result["request_count"] == result["mechanically_passed_cases"] == result["reference_checks"] == 4
    assert result["reference_matches"] == 4 and result["unrun_cases"] == []
    assert result["budget_consumed_usd"] == "0.044597248"
    assert result["unknown_usage_requests"] == 0 and result["pending_cases"] == []
    assert result["cost_coverage"] == "complete_for_reported_requests"
    assert len(batch.requests) == len({id(ledger) for ledger in batch.ledgers}) == 4
    assert [args[1:] for args, _ in batch.reads] == [("A12", 0, 1500), ("P21", 0, 1500), ("P41", 0, 1500)]
    assert all(not kwargs for _, kwargs in batch.reads)
    assert batch.key_reads == ["DASHSCOPE_API_KEY"]
    assert saved(batch.output / "summary.json") == result
    assert saved(batch.output / "authorization.json")["independent_user_consent_verified"] is False
    cases = runner.load_cases()
    for case, request, ledger, (intent, syncs), timing in zip(
            cases, batch.requests, batch.ledgers, batch.intents, result["cases"], strict=True):
        snap = runner.snapshot_for(case)
        original = runner.locator._request(case["question"], runner.build_catalog(snap))
        expected = {**original, "model": "qwen3.5-plus", "stream": False, "enable_thinking": False,
                    "parallel_tool_calls": False, "temperature": 0, "max_tokens": 512}
        assert request.content == runner._encoded(expected)
        assert request.url == base.ENDPOINT and request.method == "POST"
        assert request.headers["authorization"] == "Bearer " + KEY
        assert request.headers["accept-encoding"] == "identity"
        assert len(request.content) <= 12288
        assert len(ledger.records) == 1 and ledger.records[0]["request_id"] == 1
        reserved = json.loads(intent)
        assert reserved["event"] == "request_reserved"
        assert reserved["request_sha256"] == runner._digest(request.content)
        assert syncs[-1][str(ledger.output_dir / "events.jsonl")] == intent
        assert "assistant_message" not in ledger.records[0]
        outcome = saved(batch.output / (case["case_id"] + ".json"))
        assert outcome["mechanical_passed"] and outcome["reference_match_passed"]
        projection = outcome["result"]
        assert projection["state"] == case["expected_state"] and projection["reason"] == case["expected_reason"]
        if projection["saved_text"] is not None:
            source = next(row for row in case["sources"] if row["source_id"] == case["expected_source_id"])
            assert projection["saved_text"]["text"] == source["summary"]
            assert projection["saved_text"]["text_sha256"] == runner._digest(source["summary"].encode("utf-8"))
        assert projection["selection_relevance"] == projection["semantic_support"] == "not_assessed"
        assert 0 <= timing["elapsed_before_case_publication_seconds"] <= timing["elapsed_through_case_publication_attempt_seconds"]
        decoded = request.content.decode("ascii")
        for forbidden in (case["case_id"], "expected_source_id", "expected_state", "expected_reason", "publisher", "summary"):
            assert forbidden not in decoded
        for source in case["sources"]:
            if source["summary"]:
                assert source["summary"] not in decoded
    assert [len(request.content) for request in batch.requests] == [1786, 1959, 1765, 1785]
    assert batch.transport_options == [{"retries": 0, "verify": True, "trust_env": False}] * 4
    for options in batch.options:
        assert options["trust_env"] is options["follow_redirects"] is False and options["verify"] is True
        assert options["timeout"].connect == 10 and options["timeout"].read == 60


@pytest.mark.parametrize("choice", ["A11", None])
def test_wrong_visible_choice_is_mechanical_then_reference_failure_and_stops(batch, choice):
    """A valid wrong ID/decline is not a native failure; first mismatch cannot buy case two."""
    def change(reply, case):
        reply["choices"][0].update(message=selection(choice), finish_reason="stop" if choice is None else "tool_calls")
    batch.change = change
    result = run()
    assert len(batch.requests) == 1
    assert result["unrun_cases"] == ["SLQ02", "SLQ03", "SLQ04"]
    assert result["mechanically_passed_cases"] == result["reference_checks"] == 1
    assert result["reference_matches"] == 0 and result["reference_match_passed"] is False
    assert result["cases"][0]["gate_failure"] == "reference_mismatch"
    assert result["cases"][0]["mechanical_passed"] is True
    assert result["known_usage_estimated_usd"] != "0" and not result["batch_passed"]


def test_provider_refusal_is_not_slq03_explicit_decline_or_persisted_prose(batch):
    """A standalone refusal is mechanically valid but fails the frozen explicit-decline reference."""
    def change(reply, case):
        if case["case_id"] == "SLQ03":
            reply["choices"][0]["message"] = {"role": "assistant", "refusal": "PRIVATE_REFUSAL_DO_NOT_SAVE"}
    batch.change = change
    result = run()
    assert len(batch.requests) == 3 and result["unrun_cases"] == ["SLQ04"]
    assert result["mechanically_passed_cases"] == result["reference_checks"] == 3
    assert result["reference_matches"] == 2 and not result["batch_passed"]
    assert result["cases"][-1]["choice"] == {"kind": "refused", "source_id": None}
    assert saved(batch.output / "SLQ03.json")["result"]["reason"] == "selector_refused"
    assert len(batch.reads) == 2
    assert "PRIVATE_REFUSAL_DO_NOT_SAVE" not in "".join(path.read_text() for path in batch.output.rglob("*.json*"))


@pytest.mark.parametrize("fault", ["model", "unknown_usage", "contradictory_usage", "invalid_choice", "secret", "timeout"])
def test_native_failure_stops_without_label_check_and_preserves_cost(batch, fault, capsys):
    """Unknown is not free; rejected known usage still belongs to this batch."""
    def change(reply, case):
        if fault == "model":
            reply["model"] = "different-model"
        elif fault == "unknown_usage":
            reply.pop("usage")
        elif fault == "contradictory_usage":
            reply["usage"]["total_tokens"] = 1
        elif fault == "invalid_choice":
            reply["choices"][0]["message"] = selection("A99")
        elif fault == "secret":
            reply["unsafe"] = KEY
        else:
            raise httpx.ReadTimeout("PRIVATE_TIMEOUT " + KEY)
    batch.change = change
    assert runner.main(["--expected-commit", COMMIT, "--expected-fixture-sha256", runner.FIXTURE_SHA256,
                        "--authorize-paid", runner.PROTOCOL_IDENTITY]) == 1
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    unknown = fault in {"unknown_usage", "contradictory_usage", "timeout"}
    assert len(batch.requests) == 1 and batch.reads == []
    assert result["reference_checks"] == result["reference_matches"] == result["mechanically_passed_cases"] == 0
    assert result["reference_match_passed"] is None and result["unrun_cases"] == list(runner.CASE_IDS[1:])
    assert result["unknown_usage_requests"] == int(unknown)
    assert result["budget_consumed_usd"] == str(runner.RESERVATION_USD)
    assert (Decimal(result["known_usage_estimated_usd"]) > 0) is (not unknown)
    assert KEY not in json.dumps(result) and "PRIVATE_TIMEOUT" not in json.dumps(result)
    artifacts = "".join(path.read_text() for path in batch.output.rglob("*") if path.is_file())
    assert KEY not in artifacts + captured.out + captured.err
    assert "PRIVATE_TIMEOUT" not in artifacts + captured.out + captured.err


def test_predispatch_identity_drift_stops_before_http(batch, monkeypatch):
    """Removing the pre-dispatch check must expose a real intercepted request, not just late drift."""
    original, entries = runner.verify_identity, []

    def identity(*args):
        entries.append(args)
        if len(entries) == 2:
            path = batch.repo / "src/academic_agent/report_evidence_stage_qwen_transport.py"
            path.write_bytes(path.read_bytes() + b"\n# hidden drift\n")
        return original(*args)

    monkeypatch.setattr(runner, "verify_identity", identity)
    result = run()
    assert not batch.requests and not batch.reads
    assert result["request_count"] == result["reference_checks"] == 0
    assert result["unrun_cases"] == list(runner.CASE_IDS[1:]) and not result["batch_passed"]
    assert result["stop_reason"] == "committed_content_mismatch"


@pytest.mark.parametrize("rejected", [False, True])
def test_postcallback_identity_drift_keeps_known_usage_even_on_rejected_reply(batch, rejected):
    """The finally check runs on both normal and failing replies without refunding observed usage."""
    def drift():
        path = batch.repo / "src/academic_agent/report_evidence_stage_qwen_transport.py"
        path.write_bytes(path.read_bytes() + b"\n# changed while callback was running\n")
    batch.before_http = drift
    if rejected:
        batch.change = lambda reply, case: reply.update(model="wrong-model")
    result = run()
    assert len(batch.requests) == 1 and not batch.reads
    assert result["request_count"] == 1 and result["unknown_usage_requests"] == 0
    assert Decimal(result["known_usage_estimated_usd"]) > 0
    assert result["reference_checks"] == 0 and result["stop_reason"] == "committed_content_mismatch"


@pytest.mark.parametrize("name", runner.IDENTITY_PATHS)
def test_every_closed_identity_path_rejects_hidden_disk_drift_before_credentials(batch, name):
    """A clean git status is insufficient when the actual fixed-path disk bytes changed."""
    path = batch.repo / name
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(runner.CanaryStopped):
        run()
    assert not batch.key_reads and not batch.requests and not batch.output.exists()


@pytest.mark.parametrize("fault", ["head", "dirty", "installed", "commit_argument", "fixture_argument", "acknowledgement"])
def test_identity_and_acknowledgement_fail_before_credentials(batch, monkeypatch, fault):
    """Preflight cannot resolve credentials or create an output on a mismatched identity."""
    arguments = dict(expected_commit=COMMIT, expected_fixture_sha256=runner.FIXTURE_SHA256,
                     authorize_paid=runner.PROTOCOL_IDENTITY)
    real_git = runner._git
    if fault == "head":
        monkeypatch.setattr(runner, "_git", lambda *args: b"b" * 40 if args[0] == "rev-parse" else real_git(*args))
    elif fault == "dirty":
        monkeypatch.setattr(runner, "_git", lambda *args: b" M fixed.py" if args[0] == "status" else real_git(*args))
    elif fault == "installed":
        batch.versions["httpx"] = "999.0"
    elif fault == "commit_argument":
        arguments["expected_commit"] = "not-a-commit"
    elif fault == "fixture_argument":
        arguments["expected_fixture_sha256"] = "0" * 64
    else:
        arguments["authorize_paid"] = "report_evidence_read_first_qwen_canary_v1"
    with pytest.raises(runner.CanaryStopped):
        runner.run_canary(**arguments)
    assert not batch.key_reads and not batch.requests and not batch.output.exists()


@pytest.mark.parametrize("kind", ["file", "directory", "partially_created"])
def test_occupied_output_is_not_a_new_batch_or_credential_lookup(batch, kind):
    """Neither complete nor partially created output may be resumed or replaced."""
    if kind == "file":
        batch.output.write_text("occupied")
    else:
        batch.output.mkdir()
        if kind == "partially_created":
            (batch.output / ".identity.json.pending").write_text("partial")
    with pytest.raises(runner.CanaryStopped, match="^output_creation_failed_or_occupied$"):
        run()
    assert not batch.requests and not batch.key_reads


@pytest.mark.parametrize("where", ["source", "output_parent", "output"])
@pytest.mark.parametrize("kind", ["symlink", "reparse"])
def test_indirect_paths_rejected_without_credentials(batch, monkeypatch, where, kind):
    """Both POSIX symlink mode and Windows reparse attributes fail fixed-path admission."""
    target = (batch.repo / runner.IDENTITY_PATHS[2] if where == "source" else
              batch.output.parent if where == "output_parent" else batch.output)
    original = Path.lstat

    def indirect(path, *args, **kwargs):
        if path == target:
            return SimpleNamespace(st_mode=stat.S_IFLNK if kind == "symlink" else stat.S_IFDIR,
                                   st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT if kind == "reparse" else 0)
        return original(path, *args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "lstat", indirect)
        with pytest.raises(runner.CanaryStopped, match="^indirect_path_rejected$"):
            run()
    assert not batch.requests and not batch.key_reads


@pytest.mark.parametrize("limit", ["requests", "budget"])
def test_aggregate_gate_blocks_next_case_despite_fresh_case_ledger(batch, monkeypatch, limit):
    """Fresh per-case ledgers cannot reset the global request or reservation ceiling."""
    if limit == "requests":
        monkeypatch.setattr(runner, "MAX_REQUESTS", 1)
    else:
        monkeypatch.setattr(runner, "USD_LIMIT", runner.RESERVATION_USD)
    result = run()
    assert len(batch.requests) == result["request_count"] == 1
    assert result["reference_checks"] == result["reference_matches"] == 1
    assert len(batch.ledgers) == 2 and batch.ledgers[-1].records == []
    second_events = (batch.ledgers[-1].output_dir / "events.jsonl").read_text()
    assert "request_reserved" not in second_events
    assert result["unrun_cases"] == ["SLQ03", "SLQ04"] and not result["batch_passed"]
    assert result["stop_reason"] == ("runner_request_limit" if limit == "requests" else "runner_budget_limit")


def test_aggregate_uses_max_known_cost_and_reservation_and_unknown_stops(batch):
    """Reservations are not substituted for a larger known cost or used to continue unknown usage."""
    aggregate = runner._Batch(batch.output)
    ledger = runner.native.LocatorQwenLedger(batch.output / "SLQ01")
    aggregate.ledgers.append(ledger)
    ledger.case_id = "SLQ01"
    ledger.records.append({"reservation_usd": str(runner.RESERVATION_USD),
                           "estimated_usd": "0.041", "usage_status": "complete"})
    assert aggregate.totals()["budget_consumed_usd"] == "0.041"
    with pytest.raises(runner.CanaryStopped, match="^runner_budget_limit$"):
        aggregate.admit()
    ledger.records[0].update(estimated_usd="0.001", usage_status="unknown")
    assert aggregate.totals()["budget_consumed_usd"] == str(runner.RESERVATION_USD)
    with pytest.raises(runner.CanaryStopped, match="^runner_unresolved_or_stopped$"):
        aggregate.admit()
    assert not batch.requests


@pytest.mark.parametrize("fault", ["callback", "wire", "journal", "choice", "projection", "counter"])
def test_observation_tampering_cannot_buy_a_second_case(batch, monkeypatch, fault):
    """A coherent result/journal alone cannot replace the actual admitted callback and choice."""
    original = runner.locator.locate_saved_source

    def changed(snapshot, question, *, selector):
        result = original(snapshot, question, selector=selector)
        ledger = selector.transport.ledger
        if fault == "callback":
            selector.request["messages"][1]["content"] += " changed"
        elif fault == "wire":
            record = ledger.records[0]
            record["request"]["temperature"] = 1
            record["request_sha256"] = runner._digest(runner._encoded(record["request"]))
            events = [json.loads(line) for line in (ledger.output_dir / "events.jsonl").read_text().splitlines()]
            for event in events:
                event.update(request=record["request"], request_sha256=record["request_sha256"])
            (ledger.output_dir / "events.jsonl").write_bytes(b"".join(runner._encoded(event) + b"\n" for event in events))
        elif fault == "journal":
            path = ledger.output_dir / "events.jsonl"
            path.write_bytes(path.read_bytes().splitlines(keepends=True)[0])
        elif fault == "choice":
            selector.response = selection("A11")
        elif fault == "counter":
            result = result.model_copy(update={"callback_entries": True})
        else:
            # Internally valid alternative metadata must still match the trusted source.
            result = result.model_copy(update={"source": result.source.model_copy(update={"publisher": "forged publisher"})})
        return result

    monkeypatch.setattr(runner.locator, "locate_saved_source", changed)
    result = run()
    assert len(batch.requests) == 1 and len(batch.reads) == 1
    assert result["reference_checks"] == 0 and result["mechanically_passed_cases"] == 0
    assert result["unrun_cases"] == list(runner.CASE_IDS[1:])
    assert not result["batch_passed"] and Decimal(result["known_usage_estimated_usd"]) > 0


@pytest.mark.parametrize("event", ["request_reserved", "request_finished"])
def test_journal_persistence_failure_stops_and_keeps_spent_intent(batch, monkeypatch, event):
    """A failed reserve cannot dispatch; failed finish retains pending usage and never retries."""
    original = base.CanaryLedger._append

    def fail(self, row):
        if row["event"] == event:
            raise OSError("PRIVATE_IO " + KEY)
        return original(self, row)

    monkeypatch.setattr(base.CanaryLedger, "_append", fail)
    result = run()
    assert len(batch.requests) == int(event == "request_finished")
    assert not batch.reads and not result["batch_passed"] and result["reference_checks"] == 0
    assert result["stop_reason"] == "persistence_failed"
    if event == "request_finished":
        assert result["pending_cases"] == ["SLQ01"] and result["unknown_usage_requests"] == 0
        assert Decimal(result["known_usage_estimated_usd"]) > 0
    assert KEY not in json.dumps(result) and "PRIVATE_IO" not in json.dumps(result)


@pytest.mark.parametrize("target", ["identity.json", "experiment_manifest.json", "authorization.json",
                                   "SLQ01.json", "SLQ02.json", "SLQ03.json", "SLQ04.json", "summary.json"])
def test_publication_failure_never_reports_success_or_buys_next_request(batch, monkeypatch, target):
    """Initial, case and final publication failures have separate observed request denominators."""
    original = os.link

    def link(source, destination):
        if destination.name == target:
            raise OSError("PRIVATE_PUBLISH " + KEY)
        return original(source, destination)

    monkeypatch.setattr(runner.os, "link", link, raising=False)
    if target in {"identity.json", "experiment_manifest.json", "authorization.json"}:
        with pytest.raises(runner.CanaryStopped, match="^persistence_failed$"):
            run()
        assert not batch.requests
    else:
        result = run()
        count = 4 if target == "summary.json" else int(target[3:5])
        assert len(batch.requests) == count and not result["batch_passed"]
        assert result["unrun_cases"] == list(runner.CASE_IDS[count:])
        assert result["stop_reason"] == "persistence_failed"
        if target == "summary.json":
            assert result["summary_persisted"] is False
        else:
            assert result["cases"][-1]["case_record_persisted"] is False
    assert not (batch.output / target).exists()
    assert (batch.output / ("." + target + ".pending")).exists()


@pytest.mark.parametrize("fault", ["open", "write", "short_write", "flush", "fsync", "close"])
def test_atomic_publication_requires_complete_write_flush_sync_and_close(batch, monkeypatch, fault):
    """A pending file is not a completion marker even when all JSON bytes were written."""
    batch.output.mkdir()
    real_open = Path.open

    class Stream:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            self.stream.__enter__()
            return self

        def __exit__(self, *args):
            self.stream.__exit__(*args)
            if fault == "close":
                raise OSError(KEY)

        def write(self, raw):
            if fault == "write":
                raise OSError(KEY)
            if fault == "short_write":
                return self.stream.write(raw[:-1])
            return self.stream.write(raw)

        def flush(self):
            if fault == "flush":
                raise OSError(KEY)
            self.stream.flush()

        def fileno(self):
            return self.stream.fileno()

    def opened(path, *args, **kwargs):
        if path.name == ".case.json.pending":
            if fault == "open":
                raise OSError(KEY)
            return Stream(real_open(path, *args, **kwargs))
        return real_open(path, *args, **kwargs)

    def sync(fd):
        if fault == "fsync":
            raise OSError(KEY)
        os.fsync(fd)

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "open", opened)
        scoped.setattr(runner.os, "fsync", sync, raising=False)
        with pytest.raises(runner.CanaryStopped, match="^persistence_failed$"):
            runner._publish(batch.output, "case.json", {"completed": True})
    assert not (batch.output / "case.json").exists()


def test_duplicate_publication_preserves_original_bytes(batch):
    """Write-once linking cannot replace a previously completed case with another value."""
    batch.output.mkdir()
    runner._publish(batch.output, "case.json", {"value": 1})
    before = (batch.output / "case.json").read_bytes()
    with pytest.raises(runner.CanaryStopped, match="^persistence_failed$"):
        runner._publish(batch.output, "case.json", {"value": 2})
    assert (batch.output / "case.json").read_bytes() == before


def test_arbitrary_shared_stop_exception_is_not_a_safe_diagnostic(batch, monkeypatch):
    """The exception class alone cannot bless provider-controlled or credential-bearing text."""
    def bad(self, request):
        raise runner.CanaryStopped("PRIVATE_STOP " + KEY)
    monkeypatch.setattr(runner.native.LocatorQwenTransport, "__call__", bad)
    result = run()
    assert result["stop_reason"] == "runner_preflight_or_transport_failed"
    assert result["request_count"] == result["reference_checks"] == 0 and not batch.requests
    artifacts = "".join(path.read_text() for path in batch.output.rglob("*.json*"))
    assert KEY not in artifacts and "PRIVATE_STOP" not in artifacts


def test_default_cli_is_identity_only_and_errors_do_not_echo_arguments(batch, monkeypatch, capsys):
    """An acknowledgement is neither optional for dispatch nor independent consent attestation."""
    args = ["--expected-commit", COMMIT, "--expected-fixture-sha256", runner.FIXTURE_SHA256]
    assert runner.main(args) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "identity_only"
    assert not batch.key_reads and not batch.requests and not batch.output.exists()
    for extra in (["--unknown", KEY], ["--expected-comm", KEY]):
        with pytest.raises(SystemExit) as error:
            runner.main([*args, *extra])
        assert error.value.code == 2 and KEY not in capsys.readouterr().err
    assert runner.main([*args, "--authorize-paid", "old_protocol"]) == 1
    assert KEY not in capsys.readouterr().out and not batch.key_reads

    def bad(*args):
        raise runner.CanaryStopped(KEY)
    monkeypatch.setattr(runner, "verify_identity", bad)
    assert runner.main(args) == 1 and KEY not in capsys.readouterr().out


def test_default_cli_fresh_import_forbids_credentials_writes_and_network(batch):
    """Fresh-process import/main guards cover isolation, with git/version observations explicitly mocked."""
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
                raise AssertionError("network/process dispatch forbidden")
            if event == "open":
                path, mode, flags = args
                if isinstance(path, (str, bytes)) and Path(os.fsdecode(path)).name in {".env", "auth.json", "credentials.json"}:
                    raise AssertionError("credential file forbidden")
                if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
                    raise AssertionError("identity writes forbidden")
        sys.addaudithook(guard)
        from academic_agent import report_evidence_source_locator_canary as candidate
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
    completed = subprocess.run([sys.executable, "-B", "-c", script, str(batch.repo), COMMIT, runner.FIXTURE_SHA256],
                               cwd=REAL_ROOT, env=environment, capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert json.loads(completed.stdout)["mode"] == "identity_only"
    assert not batch.key_reads and not batch.requests and not batch.output.exists()


def test_closed_runtime_dependencies_and_fixture_identity(batch):
    """The direct adapter tuple omits its scanner's stage import; the runner closes that gap."""
    assert "src/academic_agent/report_evidence_stage_qwen_transport.py" in runner.IDENTITY_PATHS
    assert "src/academic_agent/source_pipeline.py" not in runner.IDENTITY_PATHS  # TYPE_CHECKING only.
    assert not any("read_first_canary" in name for name in runner.IDENTITY_PATHS)
    assert len(set(runner.IDENTITY_PATHS)) == len(runner.IDENTITY_PATHS)
    assert runner._digest((REAL_ROOT / runner.FIXTURE).read_bytes()) == runner.FIXTURE_SHA256
    identity = runner.verify_identity(COMMIT, runner.FIXTURE_SHA256)
    assert set(identity["disk_sha256"]) == set(identity["committed_sha256"]) == set(runner.IDENTITY_PATHS)
    assert identity["configuration"]["max_requests"] == 4
    assert identity["configuration"]["usd_soft_limit"] == "0.05"
    assert identity["configuration"]["per_case_transport"]["max_requests"] == 1
