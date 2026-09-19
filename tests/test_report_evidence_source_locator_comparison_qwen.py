"""SLCQ with real locator/adapter/Node baseline and intercepted HTTP only.

Git/version fixtures model observations, not committed live authority.
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
from academic_agent import report_evidence_source_locator_comparison_qwen as runner

REAL_ROOT = runner.ROOT
COMMIT = "a" * 40
KEY = "sk-slcq-fake-key-never-live"
USAGE = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}


def selection(source_id):
    if source_id is None:
        return {"role": "assistant", "content": '{"action":"decline"}'}
    return {"role": "assistant", "content": None, "tool_calls": [{
        "id": "fake_slcq_call", "type": "function",
        "function": {"name": "read_source", "arguments": json.dumps({"source_id": source_id})},
    }]}


def saved(path):
    return json.loads(path.read_text(encoding="utf-8"))


def run():
    return runner.run_comparison(expected_commit=COMMIT, expected_fixture_sha256=runner.FIXTURE_SHA256,
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
                            requests=[], reads=[], key_reads=[], change=None, before_http=None, before_locator=None,
                            intents=[], fsynced=[], options=[], transport_options=[], ledgers=[], baselines=[])

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
        assert len(state.baselines) == 1 and not state.output.exists()
        return KEY

    local_os = _OS()
    local_os.environ = SimpleNamespace(get=fake_key)
    monkeypatch.setattr(runner, "os", local_os)
    monkeypatch.setattr(runner, "ROOT", repo)
    monkeypatch.setattr(runner, "_git", git)
    monkeypatch.setattr(runner, "version", versions.__getitem__)
    monkeypatch.setattr(runner.baseline, "ROOT", repo)
    monkeypatch.setattr(runner.baseline, "FIXTURE", repo / runner.FIXTURE)
    monkeypatch.setattr(runner.baseline, "REPORT", repo / "examples/solid-state-batteries-ev.md")
    monkeypatch.setattr(runner.baseline, "CONTRACT", repo / "tests/js/source_browser_contract.mjs")
    state.baseline_original = runner.baseline.run_fixed_comparison

    def observed_baseline():
        assert not state.key_reads
        result = state.baseline_original()
        state.baselines.append(deepcopy(result))
        return result

    monkeypatch.setattr(runner.baseline, "run_fixed_comparison", observed_baseline)
    real_client, real_read = httpx.AsyncClient, runner.locator.read_source
    real_init, real_locate = runner.native.LocatorQwenLedger.__init__, runner.locator.locate_saved_source

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
        case = next(case for case in runner.load_fixture()["cases"] if case["question"] == body["messages"][1]["content"])
        journal = state.output / case["case_id"] / "events.jsonl"
        state.intents.append((journal.read_bytes(), deepcopy(state.fsynced)))
        for name in ("identity.json", "baseline.json", "experiment_manifest.json", "authorization.json"):
            assert saved(state.output / name)
        if state.before_http:
            state.before_http()
        ids = case["acceptable_source_ids"]
        message = selection(ids[0] if ids else None)
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

    def locate(*args, **kwargs):
        if state.before_locator:
            state.before_locator()
        return real_locate(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", transport)
    monkeypatch.setattr(httpx, "AsyncClient", client)
    monkeypatch.setattr(runner.locator, "read_source", observed_read)
    monkeypatch.setattr(runner.locator, "locate_saved_source", locate)
    return state


@pytest.mark.parametrize("fourth", ["P5", "P8"])
def test_complete_success_exact_wire_missing_text_and_paired_coverage(batch, fourth):
    """Both ambiguous titles pass membership with half coverage after real missing-text reads."""
    def change(reply, case):
        if case["case_id"] == "SLC04":
            reply["choices"][0]["message"] = selection(fourth)
    batch.change = change
    result = run()
    assert result["batch_passed"] and result["summary_persisted"]
    assert result["request_count"] == result["reference_checks"] == result["reference_matches"] == 6
    assert result["mechanically_passed_cases"] == result["observed_cases"] == result["planned_cases"] == 6
    assert result["positive_reference_cases"] == result["evaluable_positive_cases"] == 5
    assert result["no_fit_cases"] == result["evaluable_no_fit_cases"] == 1
    assert result["unrun_cases"] == result["pending_cases"] == [] and result["unknown_usage_requests"] == 0
    assert result["budget_consumed_usd"] == "0.066895872"
    assert result["reported_tokens"] == {key: value * 6 for key, value in USAGE.items()}
    assert result["cost_coverage"] == "complete_for_reported_requests"
    assert result["observed_counts"] == {
        "callback_entries": 6, "reservations": 6, "http_primitive_entries": 6, "responses_received": 6,
        "read_attempts": 5, "read_completed": 5, "evidence_texts_delivered": 0,
    }
    assert len(batch.requests) == len({id(ledger) for ledger in batch.ledgers}) == 6
    assert [args[1:] for args, _ in batch.reads] == [
        ("A2", 0, 1500), ("A4", 0, 1500), ("P7", 0, 1500), (fourth, 0, 1500), ("M1", 0, 1500)]
    assert batch.key_reads == ["DASHSCOPE_API_KEY"]
    assert saved(batch.output / "summary.json") == result
    baseline_bytes = runner._encoded(saved(batch.output / "baseline.json"))
    assert len(baseline_bytes) == 4458
    assert runner._digest(baseline_bytes) == runner.PRIMARY_BASELINE_SHA256
    auth = saved(batch.output / "authorization.json")
    assert auth["independent_user_consent_verified"] is auth["independent_review_verified"] is auth["green_ci_verified"] is False
    assert auth["standing_authorization_sources"] == [runner.PROTOCOL, runner.ERRATUM]
    experiment = saved(batch.output / "experiment_manifest.json")
    assert experiment["protocol_documents"] == [runner.PROTOCOL, runner.ERRATUM]
    assert experiment["baseline_sha256"] == runner.PRIMARY_BASELINE_SHA256
    fixture = runner.load_fixture()
    snapshot = runner.snapshot_for(fixture)
    assert all(source.summary is None and source.accessed_date == "unavailable" for source in snapshot.sources)
    identity = saved(batch.output / "identity.json")
    for case, request, ledger, (intent, syncs), outcome, bound in zip(
            fixture["cases"], batch.requests, batch.ledgers, batch.intents, result["cases"], identity["request_identities"], strict=True):
        callback = runner.locator._request(case["question"], runner.build_catalog(snapshot))
        expected = {**callback, "model": "qwen3.5-plus", "stream": False, "enable_thinking": False,
                    "parallel_tool_calls": False, "temperature": 0, "max_tokens": 512}
        assert request.content == runner._encoded(expected)
        assert bound["native_sha256"] == runner._digest(request.content) and bound["native_bytes"] == len(request.content)
        assert bound["callback_sha256"] == runner._digest(runner._encoded(callback))
        assert bound["callback_bytes"] == len(runner._encoded(callback))
        body = json.loads(request.content)
        assert [row["content"] for row in body["messages"][:2]] == [runner.locator._INSTRUCTIONS, case["question"]]
        catalog = json.loads(body["messages"][2]["content"])
        assert catalog["entries"] == [{**row, "title_truncated": False} for row in fixture["catalog"]]
        assert catalog["total_count"] == catalog["returned_count"] == 20
        assert catalog["omitted_count"] == catalog["title_truncation_count"] == 0
        assert body["tools"][0]["function"]["parameters"]["properties"]["source_id"]["enum"] == [row["source_id"] for row in fixture["catalog"]]
        # Keywords naturally occur inside titles/questions; exact whole-body
        # comparison proves absence of an extra label/keyword/report channel.
        decoded = request.content.decode("ascii")
        for forbidden in (KEY, case["case_id"], "keyword_query", "acceptable_source_ids", "reference_kind",
                          "prepared_keyword_assisted", "publisher", "summary", "report_ref", "observed_ids"):
            assert forbidden not in decoded
        assert request.url == base.ENDPOINT and request.method == "POST"
        assert request.headers["authorization"] == "Bearer " + KEY
        assert request.headers["accept-encoding"] == "identity"
        reserved = json.loads(intent)
        assert reserved["event"] == "request_reserved" and reserved["request_sha256"] == runner._digest(request.content)
        assert syncs[-1][str(ledger.output_dir / "events.jsonl")] == intent
        assert len(ledger.records) == 1 and ledger.records[0]["request_id"] == 1
        assert "assistant_message" not in ledger.records[0]
        projection = saved(batch.output / (case["case_id"] + ".json"))["result"]
        assert projection["saved_text"] is None
        assert projection["state"] == ("declined" if case["case_id"] == "SLC06" else "missing_text")
        assert projection["read_attempts"] == projection["read_completed"] == int(case["case_id"] != "SLC06")
        assert projection["semantic_support"] == projection["selection_relevance"] == "not_assessed"
        assert 0 <= outcome["elapsed_before_case_publication_seconds"] <= outcome["elapsed_through_case_publication_attempt_seconds"]
    assert [len(request.content) for request in batch.requests] == [4376, 4469, 4374, 4383, 4385, 4378]
    assert [row["callback_bytes"] for row in identity["request_identities"]] == [4253, 4346, 4251, 4260, 4262, 4255]
    pair = result["paired_candidates"][3]
    assert pair["native"]["observed_ids"] == pair["native"]["acceptable_intersection"] == [fourth]
    assert pair["native"]["reference_coverage"] == 0.5 and pair["native"]["at_least_one_acceptable_location"]
    assert pair["prepared_keyword_assisted"]["observed_ids"] == ["P5", "P8"]
    assert pair["prepared_keyword_assisted"]["reference_coverage"] == 1
    assert result["paired_candidates"][5]["native"]["no_fit_control_match"] is True
    assert batch.transport_options == [{"retries": 0, "verify": True, "trust_env": False}] * 6
    assert all(options["trust_env"] is options["follow_redirects"] is False for options in batch.options)
    assert all(options["verify"] is True and options["timeout"].connect == 10 and options["timeout"].read == 60
               for options in batch.options)


@pytest.mark.parametrize("choice", ["A1", None])
def test_wrong_visible_choice_keeps_mechanical_pass_and_stops_next_case(batch, choice):
    """Conflating reference and mechanics, or continuing after failure, changes observable counts."""
    def change(reply, case):
        reply["choices"][0].update(message=selection(choice), finish_reason="stop" if choice is None else "tool_calls")
    batch.change = change
    result = run()
    assert len(batch.requests) == result["request_count"] == 1
    assert result["reference_checks"] == result["mechanically_passed_cases"] == 1
    assert result["reference_matches"] == 0 and not result["batch_passed"]
    assert result["cases"][0]["mechanical_passed"] is True
    assert result["cases"][0]["reference_match_passed"] is False
    assert result["cases"][0]["gate_failure"] == result["stop_reason"] == "reference_mismatch"
    assert result["cases"][0]["metrics"]["observed_ids"] == ([choice] if choice else [])
    assert result["cases"][0]["metrics"]["reference_coverage"] == 0
    assert result["unrun_cases"] == list(runner.CASE_IDS[1:])
    assert len(result["cases"]) == 6 and result["positive_reference_cases"] == 5 and result["no_fit_cases"] == 1
    for row in result["cases"][1:]:
        assert row["state"] == "unrun" and all(value is None for value in row["metrics"].values())
        assert row["counts"] is row["accounting"] is row["mechanical_passed"] is row["reference_match_passed"] is None


def test_standalone_refusal_is_not_successful_empty_no_fit(batch):
    """A refusal on SLC06 has mechanical success, reference failure, and null candidate metrics."""
    def change(reply, case):
        if case["case_id"] == "SLC06":
            reply["choices"][0]["message"] = {"role": "assistant", "refusal": "PRIVATE_REFUSAL_NEVER_SAVE"}
    batch.change = change
    result = run()
    assert len(batch.requests) == result["mechanically_passed_cases"] == result["reference_checks"] == 6
    assert result["reference_matches"] == 5 and result["evaluable_no_fit_cases"] == 0 and not result["batch_passed"]
    assert result["cases"][5]["choice"] == {"kind": "refused", "source_id": None}
    assert result["cases"][5]["reference_match_passed"] is False
    assert result["cases"][5]["metrics"]["no_fit_control_match"] is None
    assert result["cases"][5]["metrics"]["observed_ids"] is None
    assert len(batch.reads) == 5
    assert "PRIVATE_REFUSAL" not in "".join(path.read_text() for path in batch.output.rglob("*.json*"))


@pytest.mark.parametrize("fault", ["model", "unknown_usage", "contradictory_usage", "invalid_choice", "secret", "timeout", "mixed"])
def test_rejected_native_reply_preserves_known_or_unknown_spend_and_safe_errors(batch, fault, capsys):
    """Rejected replies are not zero-cost or reference checks, even when usage was observed."""
    def change(reply, case):
        if fault == "model":
            reply["model"] = "wrong-model"
        elif fault == "unknown_usage":
            reply.pop("usage")
        elif fault == "contradictory_usage":
            reply["usage"]["total_tokens"] = 1
        elif fault == "invalid_choice":
            reply["choices"][0]["message"] = selection("A99")
        elif fault == "secret":
            reply["unsafe"] = KEY
        elif fault == "mixed":
            reply["choices"][0]["message"]["content"] = "PRIVATE_PROSE"
        else:
            raise httpx.ReadTimeout("PRIVATE_TIMEOUT " + KEY)
    batch.change = change
    assert runner.main(["--expected-commit", COMMIT, "--expected-fixture-sha256", runner.FIXTURE_SHA256,
                        "--authorize-paid", runner.PROTOCOL_IDENTITY]) == 1
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    unknown = fault in {"unknown_usage", "contradictory_usage", "timeout"}
    assert len(batch.requests) == 1 and not batch.reads
    assert result["reference_checks"] == result["mechanically_passed_cases"] == 0
    assert result["unknown_usage_requests"] == int(unknown)
    assert result["budget_consumed_usd"] == str(runner.RESERVATION_USD)
    assert (Decimal(result["known_usage_estimated_usd"]) > 0) is (not unknown)
    assert result["unrun_cases"] == list(runner.CASE_IDS[1:])
    artifacts = "".join(path.read_text() for path in batch.output.rglob("*") if path.is_file())
    for secret in (KEY, "PRIVATE_TIMEOUT", "PRIVATE_PROSE"):
        assert secret not in artifacts + captured.out + captured.err


def test_predispatch_identity_drift_never_enters_http(batch):
    """Changing bytes after setup checks must be caught before the actual adapter is called."""
    def drift():
        path = batch.repo / "src/academic_agent/report_evidence_stage_qwen_transport.py"
        path.write_bytes(path.read_bytes() + b"\n# drift\n")
    batch.before_locator = drift
    result = run()
    assert not batch.requests and not batch.reads and result["request_count"] == 0
    assert result["stop_reason"] == "committed_content_mismatch"
    assert result["reference_checks"] == 0 and result["unrun_cases"] == list(runner.CASE_IDS[1:])


@pytest.mark.parametrize("rejected", [False, True])
def test_postcallback_identity_drift_keeps_usage_on_success_and_exception(batch, rejected):
    """The post-call finally check cannot erase usage on accepted or rejected native replies."""
    def drift():
        path = batch.repo / "src/academic_agent/report_evidence_stage_qwen_transport.py"
        path.write_bytes(path.read_bytes() + b"\n# in-flight drift\n")
    batch.before_http = drift
    if rejected:
        batch.change = lambda reply, case: reply.update(model="wrong")
    result = run()
    assert len(batch.requests) == 1 and not batch.reads and not result["batch_passed"]
    assert result["unknown_usage_requests"] == 0 and Decimal(result["known_usage_estimated_usd"]) > 0
    assert result["reference_checks"] == 0 and result["stop_reason"] == "committed_content_mismatch"


@pytest.mark.parametrize("name", runner.IDENTITY_PATHS)
def test_every_bound_file_drift_stops_before_baseline_key_and_output(batch, name):
    """Clean status cannot attest actual bytes, including transitive imports and observer assets."""
    path = batch.repo / name
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(runner.CanaryStopped):
        run()
    assert not batch.baselines and not batch.key_reads and not batch.requests and not batch.output.exists()


@pytest.mark.parametrize("fault", ["head", "dirty", "installed", "commit_argument", "fixture_argument", "acknowledgement"])
def test_identity_and_acknowledgement_admission_before_any_paid_setup(batch, monkeypatch, fault):
    """Old allowances and mismatched identities never resolve a key or create the batch."""
    args = dict(expected_commit=COMMIT, expected_fixture_sha256=runner.FIXTURE_SHA256,
                authorize_paid=runner.PROTOCOL_IDENTITY)
    real_git = runner._git
    if fault == "head":
        monkeypatch.setattr(runner, "_git", lambda *a: b"b" * 40 if a[0] == "rev-parse" else real_git(*a))
    elif fault == "dirty":
        monkeypatch.setattr(runner, "_git", lambda *a: b" M file" if a[0] == "status" else real_git(*a))
    elif fault == "installed":
        batch.versions["httpx"] = "999"
    elif fault == "commit_argument":
        args["expected_commit"] = "invalid"
    elif fault == "fixture_argument":
        args["expected_fixture_sha256"] = "0" * 64
    else:
        args["authorize_paid"] = "report_evidence_source_locator_qwen_canary_v1"
    with pytest.raises(runner.CanaryStopped):
        runner.run_comparison(**args)
    assert not batch.baselines and not batch.key_reads and not batch.requests and not batch.output.exists()


@pytest.mark.parametrize("fault", ["node_missing", "unavailable", "changed", "integer_normalized"])
def test_baseline_failure_is_before_key_and_output(batch, monkeypatch, fault):
    """Unavailable observation and changed canonical bytes cannot become the frozen comparator."""
    if fault == "node_missing":
        monkeypatch.setattr(runner.baseline.shutil, "which", lambda _: None)
    else:
        real_baseline = runner.baseline.run_fixed_comparison

        def changed():
            value = real_baseline()
            if fault == "unavailable":
                value.update(state="unavailable", observed_cases=0)
            elif fault == "integer_normalized":
                value = json.loads(json.dumps(value), parse_float=lambda text: int(float(text)))
                assert len(runner._encoded(value)) == 4438
                assert runner._digest(runner._encoded(value)) == runner.HISTORICAL_INTEGER_NORMALIZED_BASELINE_SHA256
            else:
                value["conditions"]["prepared_keyword_assisted"][0]["observed_ids"] = ["A1"]
            return value
        monkeypatch.setattr(runner.baseline, "run_fixed_comparison", changed)
    with pytest.raises(runner.CanaryStopped, match="^baseline_unavailable_or_changed$"):
        run()
    assert not batch.key_reads and not batch.requests and not batch.output.exists()


@pytest.mark.parametrize("kind", ["file", "directory", "partial"])
def test_occupied_output_never_resumes_or_resolves_key(batch, kind):
    """No cleanup-and-rerun is allowed, even if only an incomplete publication exists."""
    if kind == "file":
        batch.output.write_text("occupied")
    else:
        batch.output.mkdir()
        if kind == "partial":
            (batch.output / ".identity.json.pending").write_text("partial")
    with pytest.raises(runner.CanaryStopped, match="^output_creation_failed_or_occupied$"):
        run()
    assert not batch.key_reads and not batch.requests


@pytest.mark.parametrize("where", ["source", "output_parent", "output"])
@pytest.mark.parametrize("kind", ["symlink", "reparse"])
def test_indirect_fixed_paths_fail_before_key(batch, monkeypatch, where, kind):
    """Both lstat symlink mode and Windows reparse attributes reject fixed paths."""
    target = (batch.repo / runner.IDENTITY_PATHS[2] if where == "source" else
              batch.output.parent if where == "output_parent" else batch.output)
    real_stat = Path.lstat

    def indirect(path, *args, **kwargs):
        if path == target:
            return SimpleNamespace(st_mode=stat.S_IFLNK if kind == "symlink" else stat.S_IFDIR,
                                   st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT if kind == "reparse" else 0)
        return real_stat(path, *args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "lstat", indirect)
        with pytest.raises(runner.CanaryStopped, match="^indirect_path_rejected$"):
            run()
    assert not batch.key_reads and not batch.requests


@pytest.mark.parametrize("limit", ["requests", "budget"])
def test_aggregate_admission_cannot_reset_with_new_case_ledger(batch, monkeypatch, limit):
    """Lowered test ceilings prevent a second reservation, regardless of per-case freshness."""
    monkeypatch.setattr(runner, "MAX_REQUESTS" if limit == "requests" else "USD_LIMIT",
                        1 if limit == "requests" else runner.RESERVATION_USD)
    result = run()
    assert len(batch.requests) == result["request_count"] == 1
    assert len(batch.ledgers) == 1 and result["reference_matches"] == 1
    assert result["stop_reason"] == ("runner_request_limit" if limit == "requests" else "runner_budget_limit")
    assert not result["batch_passed"] and result["unrun_cases"] == list(runner.CASE_IDS[2:])


def test_aggregate_max_known_reservation_unknown_pending_and_request_ceiling(batch):
    """Known cost above reserve dominates; unknown/pending or spent six requests cannot be refunded."""
    aggregate = runner._Batch(batch.output)
    ledger = runner.native.LocatorQwenLedger(batch.output / "SLC01")
    aggregate.ledgers.append(ledger)
    ledger.case_id = "SLC01"
    ledger.records.append({"reservation_usd": str(runner.RESERVATION_USD), "estimated_usd": "0.091",
                           "usage_status": "complete"})
    assert aggregate.totals()["budget_consumed_usd"] == "0.091"
    with pytest.raises(runner.CanaryStopped, match="^runner_budget_limit$"):
        aggregate.admit()
    ledger.records[0].update(estimated_usd="0.001", usage_status="unknown")
    assert aggregate.totals()["budget_consumed_usd"] == str(runner.RESERVATION_USD)
    with pytest.raises(runner.CanaryStopped, match="^runner_unresolved_or_stopped$"):
        aggregate.admit()
    ledger.records[0]["usage_status"] = "complete"
    ledger.pending = 1
    with pytest.raises(runner.CanaryStopped, match="^runner_unresolved_or_stopped$"):
        aggregate.admit()
    ledger.pending = None
    ledger.records *= 6
    with pytest.raises(runner.CanaryStopped, match="^runner_request_limit$"):
        aggregate.admit()
    assert not batch.requests


@pytest.mark.parametrize("fault", ["callback", "wire", "journal", "choice", "projection", "counter", "http_count", "http_wire", "read"])
def test_mechanical_tampering_cannot_be_promoted_by_matching_reference(batch, monkeypatch, capsys, fault):
    """Full callback, native wire, journal, actual read and complete JSON are independent seams."""
    real_locate = runner.locator.locate_saved_source
    if fault == "read":
        monkeypatch.setattr(runner.locator, "read_source", lambda *a: {"status": "missing_text"})

    def changed(snapshot, question, *, selector):
        result = real_locate(snapshot, question, selector=selector)
        ledger = selector.transport.ledger
        if fault == "callback":
            selector.request["messages"][1]["content"] += " changed"
        elif fault == "wire":
            record = ledger.records[0]
            record["request"]["temperature"] = 1
            record["request_sha256"] = runner._digest(runner._encoded(record["request"]))
            path = ledger.output_dir / "events.jsonl"
            events = [json.loads(line) for line in path.read_text().splitlines()]
            for event in events:
                event.update(request=record["request"], request_sha256=record["request_sha256"])
            path.write_bytes(b"".join(runner._encoded(event) + b"\n" for event in events))
        elif fault == "journal":
            path = ledger.output_dir / "events.jsonl"
            path.write_bytes(path.read_bytes().splitlines(keepends=True)[0])
        elif fault == "choice":
            selector.response = selection("A1")
        elif fault == "projection":
            result = result.model_copy(update={"source": result.source.model_copy(
                update={"publisher": "UNADMITTED_SOURCE_SENTINEL " + KEY})})
        elif fault == "counter":
            result = result.model_copy(update={"callback_entries": True})
        elif fault == "http_count":
            selector.http_entries = 0
        elif fault == "http_wire":
            selector.http_wire = b"{}"
        return result

    monkeypatch.setattr(runner.locator, "locate_saved_source", changed)
    assert runner.main(["--expected-commit", COMMIT, "--expected-fixture-sha256", runner.FIXTURE_SHA256,
                        "--authorize-paid", runner.PROTOCOL_IDENTITY]) == 1
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert len(batch.requests) == 1 and not result["batch_passed"]
    assert result["reference_checks"] == result["mechanically_passed_cases"] == 0
    assert result["unrun_cases"] == list(runner.CASE_IDS[1:])
    assert Decimal(result["known_usage_estimated_usd"]) > 0
    case = saved(batch.output / "SLC01.json")
    assert case["result"] is case["choice"] is None
    assert result["cases"][0]["choice"] is None
    for key in ("read_attempts", "read_completed", "evidence_texts_delivered"):
        assert case["counts"][key] is result["observed_counts"][key] is None
        assert result["count_coverage"][key] == {
            "observed_cases": 1, "available_cases": 0, "unavailable_cases": 1, "state": "not_observed"}
    assert result["observed_counts"]["http_primitive_entries"] == (0 if fault == "http_count" else 1)
    artifacts = "".join(path.read_text() for path in batch.output.rglob("*") if path.is_file())
    assert "UNADMITTED_SOURCE_SENTINEL" not in artifacts + captured.out + captured.err
    assert KEY not in artifacts + captured.out + captured.err


@pytest.mark.parametrize("event", ["request_reserved", "request_finished"])
def test_journal_persistence_failure_stops_and_retains_pending_cost(batch, monkeypatch, event):
    """Failed reserve cannot dispatch; failed finish cannot discard pending observed usage."""
    original = base.CanaryLedger._append

    def fail(self, row):
        if row["event"] == event:
            raise OSError("PRIVATE_IO " + KEY)
        return original(self, row)

    monkeypatch.setattr(base.CanaryLedger, "_append", fail)
    result = run()
    assert len(batch.requests) == int(event == "request_finished") and not batch.reads
    assert result["stop_reason"] == "persistence_failed" and not result["batch_passed"]
    if event == "request_finished":
        assert result["pending_cases"] == ["SLC01"] and Decimal(result["known_usage_estimated_usd"]) > 0
    assert KEY not in json.dumps(result) and "PRIVATE_IO" not in json.dumps(result)


@pytest.mark.parametrize("target", ["identity.json", "baseline.json", "experiment_manifest.json", "authorization.json",
                                   *(case + ".json" for case in runner.CASE_IDS), "summary.json"])
def test_publication_failure_stops_without_success_or_next_request(batch, monkeypatch, target):
    """Initial receipts precede dispatch; every case and final summary publication is required."""
    real_link = os.link

    def link(source, destination):
        if destination.name == target:
            raise OSError("PRIVATE_PUBLISH " + KEY)
        return real_link(source, destination)

    monkeypatch.setattr(runner.os, "link", link, raising=False)
    if target in {"identity.json", "baseline.json", "experiment_manifest.json", "authorization.json"}:
        with pytest.raises(runner.CanaryStopped, match="^persistence_failed$"):
            run()
        assert not batch.requests
    else:
        result = run()
        count = 6 if target == "summary.json" else int(target[3:5])
        assert len(batch.requests) == count and not result["batch_passed"]
        assert result["stop_reason"] == "persistence_failed"
        assert result["unrun_cases"] == list(runner.CASE_IDS[count:])
        if target == "summary.json":
            assert not result["summary_persisted"]
        else:
            assert not result["cases"][count - 1]["case_record_persisted"]
    assert not (batch.output / target).exists()
    assert (batch.output / ("." + target + ".pending")).exists()


@pytest.mark.parametrize("fault", ["open", "write", "short_write", "flush", "fsync", "close"])
def test_atomic_publication_requires_full_write_flush_fsync_close(batch, monkeypatch, fault):
    """Complete bytes in a pending file alone do not authorize publication."""
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
            return self.stream.write(raw[:-1] if fault == "short_write" else raw)

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


def test_write_once_publication_preserves_original(batch):
    """A later publication cannot silently replace a complete case."""
    batch.output.mkdir()
    runner._publish(batch.output, "case.json", {"value": 1})
    raw = (batch.output / "case.json").read_bytes()
    with pytest.raises(runner.CanaryStopped, match="^persistence_failed$"):
        runner._publish(batch.output, "case.json", {"value": 2})
    assert (batch.output / "case.json").read_bytes() == raw


def test_late_projection_failure_keeps_partial_count_coverage_and_complete_native_usage(batch, monkeypatch):
    """One trusted read plus a rejected read projection is partial observation, not two or zero reads."""
    original = runner.locator.locate_saved_source
    second_question = runner.load_fixture()["cases"][1]["question"]

    def changed(snapshot, question, *, selector):
        result = original(snapshot, question, selector=selector)
        if question == second_question:
            return result.model_copy(update={"source": result.source.model_copy(
                update={"publisher": "UNADMITTED_LATE_SENTINEL"})})
        return result

    monkeypatch.setattr(runner.locator, "locate_saved_source", changed)
    result = run()
    assert len(batch.requests) == len(batch.reads) == result["request_count"] == 2
    assert result["reference_matches"] == result["mechanically_passed_cases"] == 1
    assert result["reported_tokens"] == {key: value * 2 for key, value in USAGE.items()}
    assert result["unknown_usage_requests"] == 0 and result["pending_cases"] == []
    assert result["unrun_cases"] == list(runner.CASE_IDS[2:]) and not result["batch_passed"]
    assert saved(batch.output / "SLC01.json")["result"]["state"] == "missing_text"
    second = saved(batch.output / "SLC02.json")
    assert second["result"] is second["choice"] is None
    assert result["observed_counts"]["http_primitive_entries"] == 2
    for key, value in (("read_attempts", 1), ("read_completed", 1), ("evidence_texts_delivered", 0)):
        assert second["counts"][key] is None
        assert result["observed_counts"][key] == value
        assert result["count_coverage"][key] == {
            "observed_cases": 2, "available_cases": 1, "unavailable_cases": 1, "state": "partial"}
    assert "UNADMITTED_LATE_SENTINEL" not in "".join(path.read_text() for path in batch.output.rglob("*.json*"))


def test_arbitrary_shared_exception_is_not_safe_prose(batch, monkeypatch):
    """A shared exception class does not make arbitrary provider/credential text publishable."""
    def bad(self, request):
        raise runner.CanaryStopped("PRIVATE_ERROR " + KEY)
    monkeypatch.setattr(runner.native.LocatorQwenTransport, "__call__", bad)
    result = run()
    assert result["stop_reason"] == "runner_preflight_or_transport_failed"
    assert not batch.requests and result["request_count"] == 0
    artifacts = "".join(path.read_text() for path in batch.output.rglob("*.json*"))
    assert KEY not in artifacts and "PRIVATE_ERROR" not in artifacts


def test_identity_only_cli_does_not_resolve_key_run_baseline_or_create_output(batch, monkeypatch, capsys):
    """Default CLI verifies identity only; argument/error diagnostics must also be safe."""
    args = ["--expected-commit", COMMIT, "--expected-fixture-sha256", runner.FIXTURE_SHA256]
    assert runner.main(args) == 0 and json.loads(capsys.readouterr().out)["mode"] == "identity_only"
    assert not batch.baselines and not batch.key_reads and not batch.requests and not batch.output.exists()
    for extra in (["--unknown", KEY], ["--expected-comm", KEY]):
        with pytest.raises(SystemExit) as error:
            runner.main([*args, *extra])
        assert error.value.code == 2 and KEY not in capsys.readouterr().err
    assert runner.main([*args, "--authorize-paid", "old_protocol"]) == 1
    assert KEY not in capsys.readouterr().out and not batch.key_reads

    def bad(*args):
        raise RuntimeError(KEY)
    monkeypatch.setattr(runner, "verify_identity", bad)
    assert runner.main(args) == 1 and KEY not in capsys.readouterr().out


def test_fresh_import_identity_only_guards_and_actual_local_import_closure(batch):
    """Fresh-process guards reject credentials/writes/sockets; runtime imports must all be bound."""
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
                raise AssertionError("network/process forbidden")
            if event == "open":
                path, mode, flags = args
                if isinstance(path, (str, bytes)) and Path(os.fsdecode(path)).name in {".env", "auth.json", "credentials.json"}:
                    raise AssertionError("credential file forbidden")
                if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC):
                    raise AssertionError("identity write forbidden")
        sys.addaudithook(guard)
        from academic_agent import report_evidence_source_locator_comparison_qwen as candidate
        root = candidate.ROOT
        for name, module in tuple(sys.modules.items()):
            if name == "academic_agent" or name.startswith("academic_agent."):
                relative = Path(module.__file__).relative_to(root).as_posix()
                assert relative in candidate.IDENTITY_PATHS, relative
        assert "academic_agent.report_evidence_source_locator_canary" not in sys.modules
        assert "academic_agent.source_pipeline" not in sys.modules
        candidate.ROOT = Path(sys.argv[1])
        commit, fixture_hash = sys.argv[2:]
        def git(*args):
            if args[0] == "rev-parse":
                return commit.encode() + b"\n"
            if args[0] == "status":
                return b""
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


def test_identity_binds_baseline_assets_configuration_and_six_requests(batch):
    """New identity binds six exact wires and immutable baseline, without old SLQ runner."""
    identity = runner.verify_identity(COMMIT, runner.FIXTURE_SHA256)
    assert len(set(runner.IDENTITY_PATHS)) == len(runner.IDENTITY_PATHS)
    assert set(identity["disk_sha256"]) == set(identity["committed_sha256"]) == set(runner.IDENTITY_PATHS)
    assert identity["baseline_sha256"] == runner.PRIMARY_BASELINE_SHA256
    assert runner.ERRATUM in runner.IDENTITY_PATHS
    assert identity["configuration"]["protocol_documents"] == [runner.PROTOCOL, runner.ERRATUM]
    assert identity["fixture_sha256"] == runner._digest((REAL_ROOT / runner.FIXTURE).read_bytes())
    assert identity["configuration"]["max_requests"] == 6 and identity["configuration"]["usd_soft_limit"] == "0.10"
    assert identity["configuration"]["per_case_transport"]["max_requests"] == 1
    assert [row["case_id"] for row in identity["request_identities"]] == list(runner.CASE_IDS)
    assert "src/academic_agent/report_evidence_source_locator_canary.py" not in runner.IDENTITY_PATHS
