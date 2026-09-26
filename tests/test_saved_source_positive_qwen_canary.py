"""Synthetic-only native seam tests; no private inputs or real provider keys.

Git/installed-version observations are controlled evidence, not a claim that a
working implementation is committed, reviewed or authorized for live dispatch.
"""

import ast
from decimal import Decimal
import json
import os
import shutil
import stat
import subprocess
import sys
from types import SimpleNamespace
import tomllib

import httpx
import pytest

from academic_agent import report_evidence_qwen_canary as base
from academic_agent import saved_source_positive_qwen_canary as runner

REAL_ROOT = runner.ROOT
COMMIT = "a" * 40
KEY = "sk-positive-synthetic-never-real"
USAGE = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}


def selection(source_id="A1"):
    if source_id is None:
        return {"role": "assistant", "content": '{"action":"decline"}'}
    return {"role": "assistant", "content": None, "tool_calls": [{
        "id": "synthetic-call", "type": "function", "function": {
            "name": "read_source", "arguments": json.dumps({"source_id": source_id})}}]}


def saved(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.write_bytes(runner._encoded(value) + b"\n")


class LocalOS:
    def __getattr__(self, name):
        return getattr(os, name)


def synthetic_packet():
    questions = {"purpose": "synthetic controls", "authoring": "synthetic",
                 "document_paths": {"D1": "UNTRUSTED-PATH-DO-NOT-OPEN", "D2": "OTHER-LOCAL-PATH"},
                 "rubric": "synthetic-only", "cases": []}
    docs = []
    for doc_id in ("D1", "D2"):
        sources = {"academic_sources": [], "patent_sources": [], "market_sources": [],
                   "other_historical_metadata": "LOCAL-METADATA-ONLY"}
        for i in (1, 2):
            sources["academic_sources"].append({
                "source_id": f"A{i}", "title": f"Synthetic {doc_id} temperature {i}",
                "publisher": "LOCAL-PUBLISHER-ONLY", "source_type": "synthetic",
                "accessed_date": "2026-09-26", "url": "https://example.invalid/local-only",
                "evidence_summary": f" LOCAL-SAVED-{doc_id}-{i} 雪 \nexact whitespace\t",
                "summary_source": "unknown"})
        raw = runner._encoded(sources) + b"\n"
        docs.append({"doc_id": doc_id, "sources_utf8": raw.decode(), "sources_sha256": runner._digest(raw)})
    preview = []
    for i, (case_id, doc_id) in enumerate(zip(runner.CASE_IDS, runner.DOC_IDS, strict=True)):
        question = ("温度候选？" if i % 2 else "Which temperature candidate?") + str(i)
        questions["cases"].append({"case_id": case_id, "doc_id": doc_id, "question": question,
                                   "keyword_query": "LOCAL-KEYWORD-ONLY"})
        doc = next(row for row in docs if row["doc_id"] == doc_id)
        snap = runner.snapshot_from_saved_bytes(doc["sources_utf8"].encode(), doc_id)
        wire = runner._wire(runner.locator._request(question, runner.build_catalog(snap)))
        preview.append({"case_id": case_id, "body": json.loads(wire), "bytes": len(wire),
                        "sha256": runner._digest(wire)})
    qraw = runner._encoded(questions) + b"\n"
    praw = runner._encoded(preview) + b"\n"
    packet = {"schema_version": 1, "protocol_identity": runner.PROTOCOL_IDENTITY,
              "questions_utf8": qraw.decode(), "questions_sha256": runner._digest(qraw),
              "preview_sha256": runner._digest(praw), "documents": docs,
              "references": {"status": "fallible_llm_reviewed", "provenance": {
                  "reviewer_role": "synthetic_not_actual_review", "requested_model": "synthetic-not-inference",
                  "effective_model": None, "input_sha256": "1" * 64, "output_sha256": "2" * 64,
                  "limitations": "Synthetic provenance only; no actual review claimed."},
                  "cases": [{"case_id": x, "acceptable_source_ids": ["A1"]} for x in runner.CASE_IDS]}}
    return packet, preview


@pytest.fixture
def batch(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    blobs = {}
    for name in runner.IDENTITY_PATHS:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REAL_ROOT / name, path)
        blobs[name] = path.read_bytes().replace(b"\r\n", b"\n")
    (root / runner.PACKET).parent.mkdir(parents=True)
    packet, preview = synthetic_packet()
    write(root / runner.PACKET, packet)
    write(root / runner.PREVIEW, preview)
    versions = {row["name"]: row["version"] for row in tomllib.loads(
        (root / "uv.lock").read_text(encoding="utf-8"))["package"]}
    state = SimpleNamespace(root=root, output=root / runner.FIXED_OUTPUT, packet=packet, preview=preview,
                            blobs=blobs, versions=versions, calls=[], key_reads=[], reads=[], ledgers=[],
                            synced=[], options=[], transport_options=[], change=None, on_key=None,
                            on_sync=None, dirty=False, head=COMMIT)
    state.expected = {"expected_commit": COMMIT, "expected_packet_sha256": runner._digest((root / runner.PACKET).read_bytes()),
                      "expected_preview_sha256": runner._digest((root / runner.PREVIEW).read_bytes())}
    monkeypatch.setattr(runner, "ROOT", root)
    monkeypatch.setattr(runner, "version", versions.__getitem__)

    def git(*args):
        if args[0] == "rev-parse":
            return state.head.encode() + b"\n"
        if args[0] == "status":
            return b" M dirty\n" if state.dirty else b""
        assert args[0] == "show"
        return blobs[args[1].split(":", 1)[1]]

    monkeypatch.setattr(runner, "_git", git)
    local_os = LocalOS()

    def key(name):
        state.key_reads.append(name)
        assert name == "DASHSCOPE_API_KEY"
        assert saved(state.output / "claim.json")["reserved_usd"] == "0.044597248"
        assert any(".claim.json.pending" in row for row in state.synced)
        if state.on_key:
            state.on_key()
        return KEY

    local_os.environ = SimpleNamespace(get=key)

    def fsync(fd):
        os.fsync(fd)  # Real durability primitive, not a recording-only fake.
        files = {path.relative_to(state.output).as_posix(): path.read_bytes()
                 for path in state.output.rglob("*") if path.is_file()}
        state.synced.append(files)
        if state.on_sync:
            state.on_sync(files)

    local_os.fsync = fsync
    monkeypatch.setattr(runner, "os", local_os)
    base_os = LocalOS()
    base_os.fsync = fsync
    monkeypatch.setattr(base, "os", base_os)
    original_init = runner.native.LocatorQwenLedger.__init__

    def ledger_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        state.ledgers.append(self)

    monkeypatch.setattr(runner.native.LocatorQwenLedger, "__init__", ledger_init)
    original_read = runner.locator.read_source

    def read(*args):
        state.reads.append(args)
        return original_read(*args)

    monkeypatch.setattr(runner.locator, "read_source", read)
    original_client = httpx.AsyncClient

    def dispatch(request):
        state.calls.append(request)
        i = len(state.calls) - 1
        assert request.content == runner._encoded(preview[i]["body"])
        case_id = runner.CASE_IDS[i]
        journal = (state.output / case_id / "events.jsonl").read_bytes()
        assert json.loads(journal)["event"] == "request_reserved"
        assert any(row.get(f"{case_id}/events.jsonl") == journal for row in state.synced)
        assert any(f".{case_id}-intent.json.pending" in row for row in state.synced)
        response = {"model": "qwen3.5-plus", "usage": dict(USAGE), "choices": [
            {"index": 0, "message": selection(), "finish_reason": "tool_calls"}]}
        if state.change:
            state.change(response, i)
        return httpx.Response(200, stream=httpx.ByteStream(runner._encoded(response)))

    def transport(**kwargs):
        state.transport_options.append(kwargs)
        return httpx.MockTransport(dispatch)

    def client(**kwargs):
        assert isinstance(kwargs["transport"], httpx.MockTransport)
        state.options.append(kwargs)
        return original_client(**kwargs)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", transport)
    monkeypatch.setattr(httpx, "AsyncClient", client)
    return state


def run(batch):
    return runner.run_canary(**batch.expected, authorize_paid=runner.PROTOCOL_IDENTITY)


def test_actual_wire_fsync_full_read_render_and_safe_summary(batch):
    """Four real locator/transport paths must retain exact bytes and complete local text."""
    result = run(batch)
    assert result["batch_passed"] and result["summary_persisted"]
    assert result["request_count"] == result["http_entries"] == result["mechanical_passes"] == 4
    assert result["reference_checks"] == result["reference_matches"] == 4
    assert result["budget_consumed_usd"] == result["reserved_usd"] == "0.044597248"
    assert result["unknown_usage_requests"] == 0 and result["pending_cases"] == result["unrun_cases"] == []
    assert saved(batch.output / "summary.json") == result
    assert batch.key_reads == ["DASHSCOPE_API_KEY"]
    assert len(batch.reads) == len(batch.ledgers) == len(batch.calls) == 4
    assert all(type(ledger) is runner.native.LocatorQwenLedger for ledger in batch.ledgers)
    assert len({id(ledger) for ledger in batch.ledgers}) == 4
    for request, args, case_id, ledger in zip(batch.calls, batch.reads, runner.CASE_IDS, batch.ledgers, strict=True):
        assert args[1:] == ("A1", 0, 1500)
        assert request.url == base.ENDPOINT and request.method == "POST"
        assert request.headers["Authorization"] == "Bearer " + KEY
        assert request.headers["Accept-Encoding"] == "identity"
        assert ledger.records[0]["request_sha256"] == runner._digest(request.content)
        assert saved(batch.output / f"{case_id}-result.json")["status"] == "passed"
        observation = saved(batch.output / f"{case_id}-result.json")["observation"]
        text = args[0].sources[0].summary
        assert observation == {
            "selected_source_id": "A1", "state": "excerpt", "reason": "saved_text",
            "saved_text_length": len(text), "saved_text_sha256": runner._digest(text.encode("utf-8")),
            "callback_entries": 1, "callback_bytes": len(request.content) - 123,
            "read_attempts": 1, "read_completed": 1, "wire_sha256": runner._digest(request.content),
        }
        assert text not in (batch.output / f"{case_id}-result.json").read_text(encoding="utf-8")
        assert ledger.records[0]["reported_usage"] == USAGE
        wire = request.content.decode()
        for forbidden in ("LOCAL-SAVED", "LOCAL-PUBLISHER", "LOCAL-KEYWORD", "LOCAL-METADATA", "acceptable_source_ids",
                          "references", "example.invalid", KEY, "UNTRUSTED-PATH", "effective_model"):
            assert forbidden not in wire
        assert "assistant_message" not in ledger.records[0]
    assert batch.transport_options == [{"retries": 0, "verify": True, "trust_env": False}] * 4
    assert all(option["follow_redirects"] is False and option["trust_env"] is False
               and option["verify"] is True for option in batch.options)
    summary = runner._encoded(result).decode()
    assert all(x not in summary for x in (KEY, "LOCAL-SAVED", "Synthetic D1", "A1", batch.expected["expected_packet_sha256"]))


def test_identity_only_zero_key_client_output(batch, capsys, monkeypatch):
    """A verified binding is never a live-ready claim or a side-effecting preparation."""
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: pytest.fail("client constructed"))
    args = [part for key, value in batch.expected.items() for part in ("--" + key.replace("_", "-"), value)]
    assert runner.main(args) == 0
    output = json.loads(capsys.readouterr().out)
    assert output == {"mode": "identity_only", "binding": "verified", "ready": False, "live_authorized": False}
    assert batch.key_reads == batch.calls == batch.ledgers == [] and not batch.output.exists()
    (batch.root / runner.PACKET).unlink()
    assert runner.main(args) == 1
    assert json.loads(capsys.readouterr().out)["binding"] == "unavailable"
    assert not batch.output.exists()


def test_fresh_default_import_does_not_read_keys_dotenv_write_or_network(tmp_path):
    """A fresh CLI process guards imports as well as main; no real packet is inspected."""
    script = r'''
import sys, os, pathlib, socket
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
def audit(event, args):
    if event == "open":
        path, mode, flags = args
        assert not (isinstance(path, str) and pathlib.Path(path).name == ".env")
        assert not (isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT))
    assert event not in {"socket.connect", "socket.getaddrinfo"}
sys.addaudithook(audit)
old = os._Environ.__getitem__
def guarded(self, name):
    assert not any(part in name for part in ("API_KEY", "TOKEN", "SECRET"))
    return old(self, name)
os._Environ.__getitem__ = guarded
from academic_agent import saved_source_positive_qwen_canary as runner
runner.ROOT = pathlib.Path(sys.argv[2])
assert runner.main([]) == 1
'''
    result = subprocess.run([sys.executable, "-B", "-c", script, str(REAL_ROOT / "src"), str(tmp_path)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ready"] is False
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("damage", ["head", "dirty", "code", "version", "packet", "preview", "authorization"])
def test_preflight_rejects_drift_before_output_or_key(batch, damage):
    """Neither clean-status lies nor a changed private binding can reach credentials."""
    if damage == "head":
        batch.head = "b" * 40
    elif damage == "dirty":
        batch.dirty = True
    elif damage == "code":
        (batch.root / runner.IDENTITY_PATHS[3]).write_bytes(b"changed\n")
    elif damage == "version":
        batch.versions["httpx"] = "0.0.0"
    elif damage in {"packet", "preview"}:
        path = batch.root / (runner.PACKET if damage == "packet" else runner.PREVIEW)
        path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(runner.CanaryStopped):
        runner.run_canary(**batch.expected, authorize_paid="wrong" if damage == "authorization" else runner.PROTOCOL_IDENTITY)
    assert not batch.output.exists() and batch.calls == batch.key_reads == []


@pytest.mark.parametrize("kind", ["empty", "partial", "completed"])
def test_occupied_output_never_reads_key_even_new_invocation(batch, kind):
    """No completed, empty or partly created batch is reinterpreted as a fresh allowance."""
    if kind == "completed":
        assert run(batch)["batch_passed"]
        batch.calls.clear()
        batch.key_reads.clear()
    else:
        batch.output.mkdir()
        if kind == "partial":
            (batch.output / ".claim.json.pending").write_bytes(b"partial")
    with pytest.raises(runner.CanaryStopped, match="output_occupied"):
        run(batch)
    assert batch.key_reads == batch.calls == []


@pytest.mark.parametrize("choice", ["A2", None, "refusal"])
def test_reference_mismatch_separate_and_first_failure_stop(batch, choice):
    """Accepted-but-wrong selection is mechanical evidence, not reference agreement."""
    def change(reply, _):
        message = {"role": "assistant", "refusal": "UNSAFE-REFUSAL"} if choice == "refusal" else selection(choice)
        reply["choices"][0].update(message=message, finish_reason="tool_calls" if message.get("tool_calls") else "stop")
    batch.change = change
    result = run(batch)
    assert len(batch.calls) == 1 and result["unrun_cases"] == ["P02", "P03", "P04"]
    assert result["mechanical_passes"] == result["reference_checks"] == 1
    assert result["reference_matches"] == 0 and result["cases"][0]["reference_match"] is False
    assert result["stop_reason"] == ("provider_refusal" if choice == "refusal" else "reference_mismatch")
    assert "UNSAFE-REFUSAL" not in runner._encoded(result).decode()
    observation = saved(batch.output / "P01-result.json")["observation"]
    assert observation["selected_source_id"] == ("A2" if choice == "A2" else None)
    assert observation["state"] == ("excerpt" if choice == "A2" else "declined")
    if choice == "A2":
        source = batch.reads[0][0].sources[1]
        assert observation["saved_text_sha256"] == runner._digest(source.summary.encode("utf-8"))
        assert observation["saved_text_length"] == source.stored_length
    else:
        assert observation["saved_text_sha256"] is observation["saved_text_length"] is None
        assert observation["read_completed"] == 0


@pytest.mark.parametrize("failure", ["usage", "model", "invalid_selection", "timeout", "exception", "finish_fsync"])
def test_native_failure_unknown_usage_and_persistence_stop_next(batch, failure):
    """Swallowed selector errors, partial accounting and fsync faults cannot buy another case."""
    def change(reply, _):
        if failure == "usage":
            reply.pop("usage")
        elif failure == "model":
            reply["model"] = "different"
        elif failure == "invalid_selection":
            reply["choices"][0]["message"] = selection("A99")
        elif failure == "timeout":
            raise httpx.ReadTimeout("UNSAFE-ERROR-" + KEY)
        elif failure == "exception":
            raise RuntimeError("UNSAFE-ERROR-" + KEY)
    batch.change = change
    if failure == "finish_fsync":
        def on_sync(files):
            if b'request_finished' in files.get("P01/events.jsonl", b""):
                raise OSError("UNSAFE-ERROR-" + KEY)
        batch.on_sync = on_sync
    result = run(batch)
    assert not result["batch_passed"] and len(batch.calls) == 1
    assert result["mechanical_passes"] == result["reference_checks"] == 0
    assert result["unrun_cases"] == ["P02", "P03", "P04"]
    assert result["reserved_usd"] == "0.044597248"
    if failure in {"usage", "timeout", "exception"}:
        assert result["unknown_usage_requests"] == 1 and result["cost_coverage"] == "lower_bound"
    else:
        assert Decimal(result["known_usage_estimated_usd"]) > 0
    if failure == "finish_fsync":
        assert result["pending_cases"] == ["P01"]
    assert KEY not in runner._encoded(result).decode() and "UNSAFE-ERROR" not in runner._encoded(result).decode()


@pytest.mark.parametrize("when", ["before_key", "reserve", "intent", "after_http", "between_cases"])
@pytest.mark.parametrize("which", ["code", "packet", "preview"])
def test_identity_drift_around_actual_boundary(batch, when, which):
    """Drift after reserve must still block HTTP; post-call drift retains valid usage."""
    path = batch.root / {"code": runner.IDENTITY_PATHS[3], "packet": runner.PACKET, "preview": runner.PREVIEW}[which]
    damaged = False

    def damage():
        nonlocal damaged
        if not damaged:
            damaged = True
            path.write_bytes(path.read_bytes() + b" ")

    def sync(files):
        if ((when == "before_key" and ".claim.json.pending" in files)
                or (when == "reserve" and b'request_reserved' in files.get("P01/events.jsonl", b""))
                or (when == "intent" and ".P01-intent.json.pending" in files)
                or (when == "between_cases" and ".P01-result.json.pending" in files)):
            damage()

    batch.on_sync = sync
    if when == "after_http":
        batch.change = lambda reply, i: damage()
    result = run(batch)
    assert not result["batch_passed"] and damaged
    assert len(batch.calls) == (1 if when in {"after_http", "between_cases"} else 0)
    if when == "before_key":
        assert batch.key_reads == []
    if when == "after_http":
        assert Decimal(result["known_usage_estimated_usd"]) > 0
    assert "P02" in result["unrun_cases"]
    if when == "intent":
        published = saved(batch.output / "summary.json")
        assert published["http_entries"] == 0 and published["dispatch_intents"] == 1
        assert published["unknown_usage_requests"] == 1 and published["cost_coverage"] == "lower_bound"
        assert published["reserved_usd"] == "0.044597248"
        assert (batch.output / "P01-intent.json").exists()


@pytest.mark.parametrize("stage", ["claim", "reserve", "intent", "result", "summary"])
def test_real_persistence_faults_stop_and_leave_spent_output(batch, stage):
    """Failed persistence never refunds admission, even if no HTTP has happened."""
    marker = {"claim": ".claim.json.pending", "reserve": "P01/events.jsonl", "intent": ".P01-intent.json.pending",
              "result": ".P01-result.json.pending", "summary": ".summary.json.pending"}[stage]
    def sync(files):
        if marker in files and (stage != "reserve" or b'request_reserved' in files[marker]):
            raise OSError("private unsafe fsync failure")
    batch.on_sync = sync
    if stage == "claim":
        with pytest.raises(runner.CanaryStopped, match="persistence_failed"):
            run(batch)
        assert batch.key_reads == []
    else:
        result = run(batch)
        assert not result["batch_passed"]
        assert len(batch.calls) == (4 if stage == "summary" else 1 if stage == "result" else 0)
        if stage == "summary":
            assert result["summary_persisted"] is False
    assert batch.output.exists()
    with pytest.raises(runner.CanaryStopped, match="output_occupied"):
        run(batch)


@pytest.mark.parametrize("damage", ["extra_prompt", "wrong_bytes", "reference_empty", "source_hash", "duplicate_case"])
def test_packet_semantics_not_just_outer_hash(batch, damage):
    """Even explicitly re-hashed packets cannot substitute arbitrary prompt fields or incomplete references."""
    if damage == "extra_prompt":
        batch.preview[0]["body"]["messages"].append({"role": "user", "content": "LOCAL-SAVED-EXFIL"})
    elif damage == "wrong_bytes":
        batch.preview[0]["bytes"] += 1
    elif damage == "reference_empty":
        batch.packet["references"]["cases"][0]["acceptable_source_ids"] = []
    elif damage == "source_hash":
        batch.packet["documents"][0]["sources_utf8"] += " "
    else:
        batch.packet["references"]["cases"][1]["case_id"] = "P01"
    write(batch.root / runner.PREVIEW, batch.preview)
    batch.expected["expected_preview_sha256"] = runner._digest((batch.root / runner.PREVIEW).read_bytes())
    batch.packet["preview_sha256"] = batch.expected["expected_preview_sha256"]
    write(batch.root / runner.PACKET, batch.packet)
    batch.expected["expected_packet_sha256"] = runner._digest((batch.root / runner.PACKET).read_bytes())
    with pytest.raises(runner.CanaryStopped):
        run(batch)
    assert not batch.output.exists() and batch.key_reads == []


def test_actual_read_and_renderer_tampering_fail(batch, monkeypatch):
    """Correct selection alone cannot pass a damaged delivered-text seam."""
    read = runner.locator.read_source
    def changed(*args):
        result = read(*args)
        result["text"] += "CORRUPTED"
        return result
    monkeypatch.setattr(runner.locator, "read_source", changed)
    result = run(batch)
    assert result["mechanical_passes"] == result["reference_checks"] == 0
    assert len(batch.calls) == 1 and result["unrun_cases"] == ["P02", "P03", "P04"]
    assert saved(batch.output / "P01-result.json")["observation"] is None


def test_renderer_drop_fails_boundary(batch, monkeypatch):
    """Serialization is checked independently of the already validated result model."""
    original = runner.locator.render_locator_result
    def changed(result):
        value = json.loads(original(result))
        value.pop("saved_text")
        return json.dumps(value)
    monkeypatch.setattr(runner.locator, "render_locator_result", changed)
    result = run(batch)
    assert result["mechanical_passes"] == 0 and len(batch.calls) == 1


def test_aggregate_reentry_fifth_call_and_low_cost_no_refund(batch):
    """A fifth/new case ledger cannot reset aggregate admission after cheap successful calls."""
    identity = runner.verify_identity(**batch.expected)
    owner = runner._Run(identity)
    cases = runner.load_packet(batch.expected["expected_packet_sha256"], batch.expected["expected_preview_sha256"])
    for case in cases:
        ledger = runner.native.LocatorQwenLedger(owner.output / case["case_id"])
        ledger.case_id = case["case_id"]
        owner.ledgers.append(ledger)
        ledger.reserve(json.loads(case["wire"]))
        owner.dispatch(case, case["wire"], ledger)
        ledger.finish(1, received=True, usage=dict(USAGE), error=None, response_model_matches_authorized=True)
    assert owner.totals()["budget_consumed_usd"] == "0.044597248"
    fifth = runner.native.LocatorQwenLedger(owner.output / "fifth")
    fifth.reserve(json.loads(cases[0]["wire"]))
    owner.ledgers.append(fifth)
    with pytest.raises(runner.CanaryStopped, match="aggregate_limit"):
        owner.dispatch(cases[0], cases[0]["wire"], fifth)
    assert len(owner.dispatched) == 4 and batch.calls == []


def test_aggregate_over_budget_before_key(batch, monkeypatch):
    """A full-batch claim must fit before any credential lookup, not one case at a time."""
    monkeypatch.setattr(runner, "USD_LIMIT", Decimal("0.04"))
    with pytest.raises(runner.CanaryStopped, match="aggregate_limit"):
        run(batch)
    assert batch.key_reads == [] and not batch.output.exists()


@pytest.mark.parametrize("stage", ["reserve", "finish", "claim"])
def test_journal_bytes_must_match_even_after_successful_fsync(batch, stage):
    """Fsync alone cannot validate a replaced, truncated or extra journal event."""
    changed = False
    def sync(files):
        nonlocal changed
        marker = b'request_reserved' if stage == "reserve" else b'request_finished'
        if not changed and marker in files.get("P01/events.jsonl", b""):
            changed = True
            path = batch.output / ("claim.json" if stage == "claim" else "P01/events.jsonl")
            path.write_bytes(path.read_bytes() + b"{}\n")
    batch.on_sync = sync
    result = run(batch)
    assert changed and not result["batch_passed"]
    assert len(batch.calls) == (0 if stage == "reserve" else 1)
    assert result["unrun_cases"] == ["P02", "P03", "P04"]


def test_interruption_retains_pending_lower_bound_and_no_reentry(batch):
    """An interrupted native await is uncertain spend, not a free or reusable case."""
    def interrupt(reply, index):
        raise KeyboardInterrupt
    batch.change = interrupt
    result = run(batch)
    assert not result["batch_passed"] and len(batch.calls) == 1
    assert result["pending_cases"] == ["P01"] and result["unknown_usage_requests"] == 1
    assert result["cost_coverage"] == "lower_bound" and result["reserved_usd"] == "0.044597248"
    with pytest.raises(runner.CanaryStopped, match="output_occupied"):
        run(batch)


def test_second_selector_entry_and_new_ledger_do_not_reset_cap(batch):
    """An instance-local guard plus the aggregate ordering gate reject same-case re-entry."""
    identity = runner.verify_identity(**batch.expected)
    owner = runner._Run(identity)
    case = runner.load_packet(batch.expected["expected_packet_sha256"], batch.expected["expected_preview_sha256"])[0]
    ledger = runner.native.LocatorQwenLedger(owner.output / "P01")
    ledger.case_id = "P01"
    owner.ledgers.append(ledger)
    transport = runner.native.LocatorQwenTransport(KEY, ledger, snapshot=case["snapshot"], question=case["question"])
    selector = runner._CheckedSelector(transport, owner, case)
    selector(case["request"])
    with pytest.raises(runner.CanaryStopped, match="aggregate_limit"):
        selector(case["request"])
    assert len(batch.calls) == 1
    owner.stop_reason = None  # Even an incorrectly cleared stop cannot reset the spent ordering.
    other = runner.native.LocatorQwenLedger(owner.output / "second")
    other.reserve(json.loads(case["wire"]))
    owner.ledgers.append(other)
    with pytest.raises(runner.CanaryStopped, match="aggregate_limit"):
        owner.dispatch(case, case["wire"], other)
    assert len(batch.calls) == 1


def test_symlink_or_reparse_destination_rejected_before_key(batch, monkeypatch):
    """Windows reparse rejection is tested without requiring symlink creation privileges."""
    batch.output.mkdir()
    path_type = type(batch.output)
    original = path_type.lstat
    def reparse(path, *args, **kwargs):
        info = original(path, *args, **kwargs)
        if path == batch.output:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
        return info
    monkeypatch.setattr(path_type, "lstat", reparse)
    with pytest.raises(runner.CanaryStopped, match="indirect_path"):
        run(batch)
    assert batch.key_reads == batch.calls == []


def test_safe_cli_never_stringifies_arbitrary_stop_exception(batch, monkeypatch, capsys):
    """Allowlisting applies to the shared exception class too, including its stringification."""
    def failure(**kwargs):
        raise runner.CanaryStopped(KEY + " private-path hash")
    monkeypatch.setattr(runner, "run_canary", failure)
    assert runner.main(["--authorize-paid", runner.PROTOCOL_IDENTITY]) == 1
    assert json.loads(capsys.readouterr().out) == {"ready": False, "error": "runner_failed"}


def test_actual_local_import_closure_is_bound():
    """The locator secret scanner pulls in a stage transport indirectly; omitted imports are identity gaps."""
    pending = ["academic_agent.saved_source_positive_qwen_canary"]
    seen = set()
    while pending:
        module = pending.pop()
        if module in seen:
            continue
        seen.add(module)
        path = "src/" + module.replace(".", "/") + ".py"
        assert path in runner.IDENTITY_PATHS
        tree = ast.parse((REAL_ROOT / path).read_text(encoding="utf-8"))
        # Runtime imports only: TYPE_CHECKING in snapshot is deliberately excluded.
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                if node.module == "academic_agent":
                    pending.extend("academic_agent." + alias.name for alias in node.names)
                elif node.module and node.module.startswith("academic_agent."):
                    pending.append(node.module)
    assert "academic_agent.report_evidence_stage_qwen_transport" in seen
