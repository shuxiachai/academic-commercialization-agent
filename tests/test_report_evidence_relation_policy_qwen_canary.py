"""RP runner seams through the real wrapper, local read and intercepted HTTP.

Small local fixtures adapt the verified native interception pattern; no frozen
test module, old runner or synthetic adapter callback is imported. Fake identity
blobs permit testing uncommitted code without weakening the real verifier.
"""

import ast
from contextlib import contextmanager
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import tomllib
from types import SimpleNamespace

import httpx
import pytest

import report_evidence_relation_policy_canary as cli
from academic_agent import report_evidence_relation_policy_qwen_canary as runner
from academic_agent.report_evidence_relation_policy_qwen_transport import RelationPolicyQwenLedger

REAL_ROOT = runner.ROOT
KEY = "sk-rpq-fake-local-only"
COMMIT = "a" * 40
USAGE = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
SETUP = ("manifest.json", "identity.json", "experiment_manifest.json", "authorization.json")


def encoded(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def events(output):
    return [json.loads(line) for line in (output / "events.jsonl").read_text(encoding="utf-8").splitlines()]


def read(*, source_id="A1", offset=0, length=1500, content=None):
    return {"role": "assistant", "content": content, "tool_calls": [{
        "id": "rp_native_read", "type": "function", "function": {"name": "read_source", "arguments": json.dumps({
            "source_id": source_id, "offset": offset, "length": length})}}]}


def final(body, relation):
    tool = json.loads(body["messages"][-1]["content"])
    return {"role": "assistant", "content": json.dumps({
        "claim_relation": relation, "answer": "Scripted runner control; not native judgment.",
        "supporting_evidence_ids": [tool["evidence_id"]] if relation in {"supported", "refuted"} else [],
        "caveats": ["Saved synthetic text only."],
    })}


def payload(message, **changes):
    return {"model": "qwen3.5-plus", "usage": deepcopy(USAGE), "choices": [{
        "index": 0, "message": message, "finish_reason": "tool_calls" if message.get("tool_calls") else "stop",
    }], **changes}


def response(value):
    return httpx.Response(200, stream=httpx.ByteStream(encoded(value)))


def provider(request):
    body = json.loads(request.content)
    if body["tool_choice"] == "auto":
        return response(payload(read()))
    # References are server-side scripted controls, never part of the request.
    case = next(case for case in runner.load_cases() if case["claim"] == body["messages"][1]["content"])
    return response(payload(final(body, case["expected_relation"])))


@pytest.fixture(autouse=True)
def offline(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    committed = {}
    for name in runner.IDENTITY_PATHS:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REAL_ROOT / name, path)
        committed[name] = path.read_bytes().replace(b"\r\n", b"\n")
    (repo / "outputs").mkdir()
    versions = {row["name"]: row["version"] for row in tomllib.loads(
        (repo / "uv.lock").read_text(encoding="utf-8"))["package"]}
    state = SimpleNamespace(repo=repo, committed=committed, versions=versions, requests=[], intents=[],
                            key_reads=[], key=KEY, handler=provider, output=repo / runner.FIXED_OUTPUT,
                            clients=[], transports=[], tool_reads=[], git=[])

    def git(*args):
        state.git.append(args)
        if args[0] == "rev-parse":
            return COMMIT.encode() + b"\n"
        if args[0] == "status":
            return b""
        if args[0] == "show":
            commit, name = args[1].split(":", 1)
            assert commit == COMMIT
            return committed[name]
        pytest.fail("unexpected Git operation")

    class Environment:
        def get(self, name):
            state.key_reads.append(name)
            assert name == "DASHSCOPE_API_KEY"
            return state.key

    class OS:
        environ = Environment()

        def __getattr__(self, name):
            return getattr(os, name)

    monkeypatch.setattr(runner, "ROOT", repo)
    monkeypatch.setattr(runner, "_git", git)
    monkeypatch.setattr(runner, "version", versions.__getitem__)
    monkeypatch.setattr(runner, "os", OS())
    real_client, real_read = httpx.AsyncClient, runner.core.read_source
    real_pair, real_connect = socket.socketpair, socket.socket.connect
    creating_pair = False

    def forbidden(*args, **kwargs):
        pytest.fail("non-intercepted network is forbidden")

    def self_pipe(*args, **kwargs):
        # Windows asyncio owns a synchronous stdlib loopback socketpair. This
        # exception is IPC only, not permission for arbitrary loopback HTTP.
        nonlocal creating_pair
        creating_pair = True
        try:
            return real_pair(*args, **kwargs)
        finally:
            creating_pair = False

    def connect(sock, address):
        if creating_pair and isinstance(address, tuple) and address[0] in {"127.0.0.1", "::1"}:
            return real_connect(sock, address)
        forbidden()

    async def dispatch(request):
        state.requests.append(request)
        state.intents.append(events(state.output)[-1])
        for name in SETUP:
            assert (state.output / name).is_file()
        return state.handler(request)

    def transport(**kwargs):
        state.transports.append(kwargs)
        return httpx.MockTransport(dispatch)

    def client(**kwargs):
        state.clients.append(kwargs)
        if (not isinstance(kwargs.get("transport"), httpx.MockTransport)
                or kwargs.get("trust_env") is not False or kwargs.get("proxy") is not None or kwargs.get("mounts")):
            forbidden()
        return real_client(**kwargs)

    def observe_read(*args, **kwargs):
        state.tool_reads.append(deepcopy(kwargs))
        return real_read(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", transport)
    monkeypatch.setattr(httpx, "AsyncClient", client)
    monkeypatch.setattr(httpx, "HTTPTransport", forbidden)
    monkeypatch.setattr(httpx, "Client", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "socketpair", self_pipe)
    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(runner.core, "read_source", observe_read)
    return state


def arguments(paid=False):
    result = ["--expected-commit", COMMIT, "--expected-fixture-sha256", runner.FIXTURE_SHA256]
    return result + (["--authorize-paid", runner.PROTOCOL_IDENTITY] if paid else [])


def batch():
    return runner.run_canary(expected_commit=COMMIT, expected_fixture_sha256=runner.FIXTURE_SHA256,
                             authorize_paid=runner.PROTOCOL_IDENTITY)


def no_effects(state):
    assert not state.requests and not state.key_reads
    assert list((state.repo / "outputs").iterdir()) == []


def test_identity_only_cli_and_exact_projection(offline, capsys):
    """The default path verifies identity without importing old execution paths."""
    assert cli.main(arguments()) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["mode"] == "identity_only" and shown["live_authorized"] is False
    identity = shown["identity"]
    assert set(identity["disk_sha256"]) == set(identity["committed_sha256"]) == set(runner.IDENTITY_PATHS)
    assert identity["configuration_sha256"] == hashlib.sha256(encoded(runner.configuration())).hexdigest()
    cases = runner.load_cases()
    assert [case["case_id"] for case in cases] == ["RP01", "RP02", "RP03"]
    assert [case["expected_relation"] for case in cases] == ["insufficient", "refuted", "supported"]
    for case in cases:
        snapshot = runner.snapshot_for(case)
        source = snapshot.sources[0].model_dump()
        assert snapshot.report_ref == case["case_id"] and source["summary"] == case["text"]
        assert {key: source[key] for key in runner.SOURCE_METADATA} == runner.SOURCE_METADATA
    no_effects(offline)


def test_static_and_fresh_import_closure(offline):
    """Include the RP adapter itself and entrypoints, not only its coupling list."""
    assert runner.RelationPolicyQwenLedger is RelationPolicyQwenLedger
    pending = ["src/academic_agent/report_evidence_relation_policy_qwen_canary.py", "report_evidence_relation_policy_canary.py"]
    seen = set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        assert name in runner.IDENTITY_PATHS
        for node in ast.parse((REAL_ROOT / name).read_text(encoding="utf-8")).body:
            if isinstance(node, ast.ImportFrom) and node.module:
                modules = (["academic_agent." + alias.name for alias in node.names]
                           if node.module == "academic_agent" else [node.module])
                pending.extend("src/" + module.replace(".", "/") + ".py"
                               for module in modules if module.startswith("academic_agent."))
    assert "src/academic_agent/report_evidence_relation_policy_qwen_transport.py" in seen
    assert not any("contrast" in name or "claim_qwen" in name or "real_saved" in name for name in seen)
    script = r'''
import builtins, os, pathlib, socket, sys
import httpx
def blocked(*args, **kwargs):
    raise AssertionError("forbidden import effect")
original_open = builtins.open
def opened(path, *args, **kwargs):
    if isinstance(path, (str, bytes, os.PathLike)) and pathlib.Path(path).name == ".env":
        blocked()
    return original_open(path, *args, **kwargs)
builtins.open = opened
original_get = os._Environ.get
def getenv(self, name, *args):
    if "KEY" in name or name.startswith(("DASHSCOPE", "OPENAI")):
        blocked()
    return original_get(self, name, *args)
os._Environ.get = getenv
pathlib.Path.mkdir = blocked
httpx.AsyncClient = httpx.Client = socket.create_connection = blocked
import report_evidence_relation_policy_canary
from academic_agent import report_evidence_relation_policy_qwen_canary as runner
assert "dotenv" not in sys.modules
for name, module in tuple(sys.modules.items()):
    if name.startswith("academic_agent") and getattr(module, "__file__", None):
        path = pathlib.Path(module.__file__).resolve().relative_to(runner.ROOT).as_posix()
        assert path in runner.IDENTITY_PATHS, path
        assert not any(x in name for x in ("claim_qwen", "contrast", "real_saved", "guarded_followup"))
print("safe_import")
'''
    env = {name: os.environ[name] for name in ("SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP") if name in os.environ}
    env["PYTHONPATH"] = os.pathsep.join((str(REAL_ROOT), str(REAL_ROOT / "src")))
    process = subprocess.run([sys.executable, "-B", "-c", script], cwd=REAL_ROOT, env=env,
                             capture_output=True, text=True, check=False, timeout=30)
    assert process.returncode == 0, process.stderr
    assert process.stdout.strip() == "safe_import"
    no_effects(offline)


@pytest.mark.parametrize("name", runner.IDENTITY_PATHS)
def test_hidden_disk_change_precedes_key(offline, name):
    """Clean git status is insufficient when any executing/authority file differs."""
    path = offline.repo / name
    path.write_bytes(path.read_bytes() + b"\n# hidden edit\n")
    with pytest.raises(runner.CanaryStopped, match="committed_content_mismatch"):
        batch()
    no_effects(offline)


@pytest.mark.parametrize("name", runner.DEPENDENCIES)
def test_every_installed_dependency_is_bound(offline, name):
    """Transitive HTTP and model-validation versions are not silently omitted."""
    offline.versions[name] = "0.0.0"
    with pytest.raises(runner.CanaryStopped, match="installed_dependency_mismatch"):
        batch()
    no_effects(offline)


@pytest.mark.parametrize("fault", ["fixture_bytes", "fixture_crlf", "attributes", "missing", "dirty", "commit", "git_error"])
def test_identity_admission_failure_has_no_side_effects(offline, monkeypatch, fault):
    """Fixture raw identity is stricter than allowed fixed-source newline normalization."""
    if fault in {"fixture_bytes", "fixture_crlf", "attributes", "missing"}:
        name = ".gitattributes" if fault == "attributes" else runner.FIXTURE
        path = offline.repo / name
        raw = path.read_bytes()
        if fault == "missing":
            path.unlink()
        else:
            raw = raw.replace(b"\n", b"\r\n") if fault == "fixture_crlf" else raw + b"\n"
            path.write_bytes(raw)
            offline.committed[name] = raw.replace(b"\r\n", b"\n")
    else:
        original = runner._git

        def changed(*args):
            if fault == "git_error":
                raise subprocess.CalledProcessError(1, ["git"])
            if args[0] == ("status" if fault == "dirty" else "rev-parse"):
                return b"changed"
            return original(*args)
        monkeypatch.setattr(runner, "_git", changed)
    with pytest.raises(runner.CanaryStopped):
        batch()
    no_effects(offline)


@pytest.mark.parametrize("option", ["--force", "--resume", "--output", "--case", "--model", "--expected-c"])
def test_cli_scope_cannot_expand_or_echo_arguments(offline, capsys, option):
    """Unknown options cannot add another batch or leak arbitrary argv text."""
    with pytest.raises(SystemExit) as exc:
        cli.main(arguments() + [option, KEY])
    assert exc.value.code == 2
    assert KEY not in capsys.readouterr().err
    no_effects(offline)


@pytest.mark.parametrize("ack", ["report_evidence_claim_contrast_qwen_canary_v1", "", True])
def test_only_new_acknowledgement_is_accepted(offline, ack):
    """Old consumed allowance identities are not authority for RP."""
    with pytest.raises(runner.CanaryStopped, match="fresh_protocol_acknowledgement_required"):
        runner.run_canary(expected_commit=COMMIT, expected_fixture_sha256=runner.FIXTURE_SHA256, authorize_paid=ack)
    no_effects(offline)


@pytest.mark.parametrize("key", [None, "", "bad key"])
def test_key_admission_never_falls_back(offline, key):
    """Only the fake dedicated process selection is consulted, never an ambient key."""
    offline.key = key
    with pytest.raises(runner.CanaryStopped):
        batch()
    assert offline.key_reads == ["DASHSCOPE_API_KEY"] and not offline.requests
    assert not offline.output.exists()


def test_full_six_requests_three_distinct_delivery_layers(offline, capsys):
    """Real RP callbacks, complete local reads and native HTTP journals agree."""
    assert cli.main(arguments(True)) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary == read_json(offline.output / "summary.json")
    assert summary["batch_passed"] and summary["mechanical_passed"] and summary["label_match_passed"]
    assert summary["summary_persisted"] and summary["semantic_review"] == "pending"
    assert summary["request_count"] == 6 and summary["unknown_usage_requests"] == 0
    assert summary["stop_reason"] is None and summary["pending_request_id"] is None
    assert summary["unrun_cases"] == [] and len(offline.tool_reads) == 3
    assert Decimal(summary["budget_consumed_usd"]) == runner.RESERVATION_USD * 6
    manifest = read_json(offline.output / "manifest.json")
    assert manifest["transport_identity"] == runner.TRANSPORT_IDENTITY
    assert manifest["live_authorization"] is False
    assert read_json(offline.output / "authorization.json")["independent_user_consent_verified"] is False
    receipt_ids = []
    for index, case in enumerate(runner.load_cases()):
        result = read_json(offline.output / (case["case_id"] + ".json"))["result"]
        inner, audit = result["inner"], result["audit"]
        assert inner["claim"] == case["claim"] and inner["model_assessment"]["claim_relation"] == case["expected_relation"]
        assert inner["semantic_support"] == "not_assessed" and inner["answer_verification"] == "not_verified"
        assert inner["assessment_origin"] == "injected_transport_unverified"
        receipt = inner["served_evidence"][0]
        assert receipt["text"] == case["text"] and receipt["window_truncated"] is False
        receipt_ids.append(receipt["evidence_id"])
        for stage in range(2):
            request, intent = offline.requests[2 * index + stage], offline.intents[2 * index + stage]
            body = json.loads(request.content)
            assert request.content == encoded(intent["request"])
            assert hashlib.sha256(request.content).hexdigest() == intent["request_sha256"]
            assert len(request.content) <= 12288 and body["messages"][1]["content"] == case["claim"]
            assert body["messages"][0]["content"].count(runner.policy.POLICY_APPEND) == 1
            assert body["messages"][0]["content"].count(runner.claim_policy._NEW_FINAL) == 1
            assert b"expected_relation" not in request.content and b"proposition_kind" not in request.content
            assert case["reference_rationale"].encode() not in request.content
            callback = {"messages": body["messages"], "tools": body.get("tools", []), "tool_choice": body["tool_choice"]}
            entry = audit["callback_entries"][stage]
            assert entry["request_hash"] == hashlib.sha256(encoded(callback)).hexdigest()
            assert entry["request_bytes"] == len(encoded(callback)) and entry["ordinal"] == stage + 1
            assert entry["policy_hash"] == audit["configured_policy_hash"] == runner.FROZEN_POLICY_SHA256
            claim_callback = deepcopy(callback)
            claim_callback["messages"][0]["content"] = body["messages"][0]["content"].removesuffix(runner.policy.POLICY_APPEND)
            catalog_callback = deepcopy(claim_callback)
            catalog_callback["messages"][0]["content"] = claim_callback["messages"][0]["content"].replace(
                runner.claim_policy._NEW_FINAL, runner.claim_policy._OLD_FINAL, 1)
            assert inner["audit"]["callback_bytes"][stage] == len(encoded(claim_callback)) < entry["request_bytes"]
            assert inner["audit"]["catalog"]["callback_bytes"][stage] == len(encoded(catalog_callback))
            expected_ids = [receipt["evidence_id"]] if stage else []
            assert entry["delivered_read_ids"] == entry["usable_read_ids"] == expected_ids
            if stage:
                assert "tools" not in body and body["response_format"] == {"type": "json_object"}
                tool = json.loads(body["messages"][-1]["content"])
                assert tool["text"] == receipt["text"] and tool["evidence_id"] == receipt["evidence_id"]
            else:
                assert "response_format" not in body and body["tool_choice"] == "auto"
    assert len(set(receipt_ids)) == 3  # Shared text never shares snapshot identity.
    assert len(offline.requests) == 6
    assert all(options == {"retries": 0, "verify": True, "trust_env": False} for options in offline.transports)


def tamper_result(monkeypatch, transform):
    original = runner.policy.run_relation_policy_followup

    def changed(*args, **kwargs):
        return transform(original(*args, **kwargs))
    monkeypatch.setattr(runner.policy, "run_relation_policy_followup", changed)


@pytest.mark.parametrize("fault", ["missing", "configured_policy_id", "configured_policy_hash", "blocked_reason",
                                  "callback_exception_type", "ordinal", "request_hash", "request_bytes", "policy_hash",
                                  "delivered_read_ids", "usable_read_ids", "read_result_reason"])
def test_policy_audit_admission_stops_actual_dispatch(offline, monkeypatch, fault):
    """A valid inner/native exchange cannot substitute for a forged RP audit."""
    def change(result):
        audit = result.audit
        if fault == "missing":
            audit = audit.model_copy(update={"callback_entries": ()})
        elif fault in {"configured_policy_id", "configured_policy_hash", "blocked_reason", "callback_exception_type"}:
            audit = audit.model_copy(update={fault: "wrong"})
        else:
            entries = list(audit.callback_entries)
            value = {"ordinal": 9, "request_bytes": 7, "delivered_read_ids": (), "usable_read_ids": ()}.get(fault, "wrong")
            entries[1] = entries[1].model_copy(update={fault: value})
            audit = audit.model_copy(update={"callback_entries": tuple(entries)})
        return result.model_copy(update={"audit": audit})
    tamper_result(monkeypatch, change)
    result = batch()
    assert len(offline.requests) == 2
    assert result["batch_passed"] is False and result["cases"][0]["mechanical_passed"] is False
    assert result["unrun_cases"] == ["RP02", "RP03"]
    assert result["stop_reason"] == "relation_policy_audit_failed"


@pytest.mark.parametrize("fault", ["partial", "offset", "wrong_source", "early_final"])
def test_first_stage_full_read_stops_before_second_http(offline, fault):
    """General adapter partial-read support must not buy this batch's second turn."""
    def handler(request):
        body = json.loads(request.content)
        if body["tool_choice"] == "auto":
            message = {"partial": read(length=1), "offset": read(offset=1), "wrong_source": read(source_id="A2"),
                       "early_final": {"role": "assistant", "content": "{}"}}[fault]
            return response(payload(message))
        return provider(request)  # Valid reply available if the early guard is removed.
    offline.handler = handler
    result = batch()
    assert len(offline.requests) == 1
    assert result["batch_passed"] is False and result["unknown_usage_requests"] == 0
    assert result["request_count"] == 1 and result["unrun_cases"] == ["RP02", "RP03"]
    assert not offline.tool_reads


@pytest.mark.parametrize("case_index", [0, 1, 2])
def test_label_stop_preserves_mechanical_success(offline, case_index):
    """Wrong-but-valid relations stop new cases without rewriting native answers."""
    claims = [case["claim"] for case in runner.load_cases()]

    def handler(request):
        body = json.loads(request.content)
        if body["tool_choice"] == "none" and body["messages"][1]["content"] == claims[case_index]:
            relation = "supported" if case_index != 2 else "refuted"
            return response(payload(final(body, relation)))
        return provider(request)
    offline.handler = handler
    result = batch()
    assert len(offline.requests) == 2 * (case_index + 1)
    assert result["cases"][-1]["mechanical_passed"] is True
    assert result["cases"][-1]["label_match_passed"] is False
    assert result["label_match_passed"] is False and result["batch_passed"] is False
    assert result["mechanically_passed_cases"] == case_index + 1
    assert result["stop_reason"] == "expected_relation_mismatch"


@pytest.mark.parametrize("layer,field", [("rp", "ordinal"), ("rp", "request_bytes"), ("claim", "downstream_calls"),
                                       ("catalog", "total_count"), ("core", "tool_executions"), ("core", "no_tools")])
def test_raw_counter_types_cannot_be_normalized_into_success(offline, monkeypatch, layer, field):
    """Inspect raw types before serialization can conceal bool/int substitution."""
    def change(result):
        value = 0 if field == "no_tools" else True
        if layer == "rp":
            entries = list(result.audit.callback_entries)
            entries[0] = entries[0].model_copy(update={field: value})
            return result.model_copy(update={"audit": result.audit.model_copy(update={"callback_entries": tuple(entries)})})
        inner = result.inner
        audit = inner.audit
        if layer == "claim":
            audit = audit.model_copy(update={field: value})
        else:
            catalog = audit.catalog
            catalog = (catalog.model_copy(update={field: value}) if layer == "catalog" else
                       catalog.model_copy(update={"core": catalog.core.model_copy(update={field: value})}))
            audit = audit.model_copy(update={"catalog": catalog})
        return result.model_copy(update={"inner": inner.model_copy(update={"audit": audit})})
    tamper_result(monkeypatch, change)
    result = batch()
    assert len(offline.requests) == 2 and result["batch_passed"] is False
    assert result["cases"][0]["mechanical_passed"] is False


@pytest.mark.parametrize("fault", ["receipt", "claim", "claim_bytes", "catalog_bytes", "semantic_flag", "assessment"])
def test_inner_and_serialized_receipt_are_not_replaced_by_rp_audit(offline, monkeypatch, fault):
    """Good outer policy delivery does not excuse invalid frozen inner observations."""
    def change(result):
        inner = result.inner
        if fault == "receipt":
            receipt = inner.served_evidence[0].model_copy(update={"text": "forged"})
            inner = inner.model_copy(update={"served_evidence": (receipt,)})
        elif fault == "claim":
            inner = inner.model_copy(update={"claim": inner.claim + " "})
        elif fault in {"claim_bytes", "catalog_bytes"}:
            audit = inner.audit
            audit = (audit.model_copy(update={"callback_bytes": (1, 2)}) if fault == "claim_bytes" else
                     audit.model_copy(update={"catalog": audit.catalog.model_copy(update={"callback_bytes": (1, 2)})}))
            inner = inner.model_copy(update={"audit": audit})
        elif fault == "semantic_flag":
            inner = inner.model_copy(update={"semantic_support": "verified"})
        else:
            inner = inner.model_copy(update={"model_assessment": inner.model_assessment.model_copy(update={"answer": "substituted"})})
        return result.model_copy(update={"inner": inner})
    tamper_result(monkeypatch, change)
    result = batch()
    assert len(offline.requests) == 2 and result["batch_passed"] is False


@pytest.mark.parametrize("fault", ["model", "unknown_usage", "invalid_final", "timeout"])
def test_native_failure_keeps_accounting_and_stops(offline, fault):
    """Rejected responses and uncertain requests still belong in budget accounting."""
    def handler(request):
        body = json.loads(request.content)
        if fault == "timeout":
            raise httpx.ReadTimeout("invented failure")
        if fault == "model":
            return response(payload(read(), model="wrong-model"))
        if fault == "unknown_usage":
            return response(payload(read(), usage=None))
        if body["tool_choice"] == "none":
            return response(payload({"role": "assistant", "content": "{}"}))
        return provider(request)
    offline.handler = handler
    result = batch()
    expected = 2 if fault == "invalid_final" else 1
    assert len(offline.requests) == result["request_count"] == expected
    assert result["unknown_usage_requests"] == int(fault in {"unknown_usage", "timeout"})
    assert Decimal(result["budget_consumed_usd"]) >= runner.RESERVATION_USD * expected
    assert result["batch_passed"] is False and result["unrun_cases"] == ["RP02", "RP03"]


@pytest.mark.parametrize("boundary", [1, 2, 3, 4])
@pytest.mark.parametrize("rejected", [False, True])
def test_pre_post_identity_drift_preserves_observed_usage(offline, monkeypatch, boundary, rejected):
    """Both calls' finally checks run after successful and rejected responses."""
    original = runner.verify_identity
    checks = 0
    check_trace = []

    def verify(*args):
        nonlocal checks
        identity = original(*args)
        checks += 1
        check_trace.append(len(offline.requests))
        if checks == boundary + 1:  # Initial batch identity precedes four per-call checks.
            return {**identity, "configuration_sha256": "changed"}
        return identity
    monkeypatch.setattr(runner, "verify_identity", verify)

    def handler(request):
        if rejected and len(offline.requests) == (boundary + 1) // 2:
            return response(payload(read(), model="wrong"))
        return provider(request)
    offline.handler = handler
    result = batch()
    count = boundary // 2
    # A provider refusal also stops dispatch: request counts alone cannot
    # prove the finally check ran. Observe its invocation after the rejection.
    assert checks == boundary + 1
    assert check_trace == [0, 0, 1, 1, 2][:boundary + 1]
    assert len(offline.requests) == count and result["request_count"] == count
    assert result["unknown_usage_requests"] == 0
    assert result["batch_passed"] is False
    if count:
        finished = [row for row in events(offline.output) if row["event"] == "request_finished"]
        assert all(row["reported_usage"] == USAGE for row in finished)


@pytest.mark.parametrize("occupied", ["directory", "partial", "file"])
def test_output_is_exclusive_before_key(offline, occupied):
    """Even empty or incomplete old output cannot be resumed or overwritten."""
    if occupied == "file":
        offline.output.write_text("occupied", encoding="utf-8")
    else:
        offline.output.mkdir()
        if occupied == "partial":
            (offline.output / ".summary.json.pending").write_text("occupied", encoding="utf-8")
    with pytest.raises(runner.CanaryStopped):
        batch()
    assert not offline.requests and not offline.key_reads


@pytest.mark.parametrize("target,expected", [("identity.json", 0), ("experiment_manifest.json", 0),
                                          ("authorization.json", 0), ("RP01.json", 2), ("RP03.json", 6), ("summary.json", 6)])
@pytest.mark.parametrize("fault", ["write", "flush", "fsync", "close", "publish"])
def test_publication_failure_cannot_buy_next_case(offline, monkeypatch, target, expected, fault):
    """Only flushed/fsynced/closed write-once results may satisfy publication."""
    original_open, original_link, original_fsync = Path.open, os.link, os.fsync
    descriptors = set()

    class Stream:
        def __init__(self, stream):
            self.stream = stream

        def __getattr__(self, name):
            return getattr(self.stream, name)

        def __enter__(self):
            self.stream.__enter__()
            descriptors.add(self.stream.fileno())
            return self

        def write(self, raw):
            if fault == "write":
                raise OSError("injected write loss")
            return self.stream.write(raw)

        def flush(self):
            if fault == "flush":
                raise OSError("injected flush loss")
            return self.stream.flush()

        def __exit__(self, *args):
            descriptors.discard(self.stream.fileno())
            result = self.stream.__exit__(*args)
            if fault == "close":
                raise OSError("injected close loss")
            return result

    def opened(path, mode="r", *args, **kwargs):
        stream = original_open(path, mode, *args, **kwargs)
        if mode == "xb" and path.parent == offline.output and path.name in {target, "." + target + ".pending"}:
            return Stream(stream)
        return stream

    def fsync(fd):
        if fault == "fsync" and fd in descriptors:
            raise OSError("injected fsync loss")
        return original_fsync(fd)

    def link(source, destination):
        if fault == "publish" and Path(destination).name == target:
            raise OSError("injected link loss")
        return original_link(source, destination)

    monkeypatch.setattr(Path, "open", opened)
    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "link", link)
    if expected == 0:
        with pytest.raises(runner.CanaryStopped):
            batch()
    else:
        result = batch()
        assert result["batch_passed"] is False
        assert result["mechanically_passed_cases"] == expected // 2
        assert result["cases"][-1]["mechanical_passed"] is True
        if target == "summary.json":
            assert result["summary_persisted"] is False and result["label_match_passed"] is True
            assert not (offline.output / target).exists()
        else:
            assert result["cases"][-1]["case_record_persisted"] is False
    assert len(offline.requests) == expected


def test_two_callbacks_one_http_preserves_actual_policy_delivery(offline, monkeypatch, tmp_path):
    """Final JSON mode may refuse HTTP after RP has delivered a complete receipt."""
    # A distinct fresh fake repo leaves the valid probe's occupied output intact.
    assert batch()["batch_passed"] is True
    padding = 12289 - len(offline.requests[1].content) + 2  # null -> "" saves two bytes.
    assert 0 < padding < 16000
    repo = tmp_path / "second-repo"
    shutil.copytree(offline.repo, repo, ignore=shutil.ignore_patterns("outputs"))
    (repo / "outputs").mkdir()
    monkeypatch.setattr(runner, "ROOT", repo)
    offline.repo, offline.output = repo, repo / runner.FIXED_OUTPUT
    offline.requests.clear()
    offline.intents.clear()
    offline.tool_reads.clear()
    callbacks = []
    original = runner._CheckedTransport.__call__

    def checked(self, request, /):
        callbacks.append(deepcopy(request))
        return original(self, request)

    def handler(request):
        if json.loads(request.content)["tool_choice"] == "auto":
            return response(payload(read(content="x" * padding)))
        return provider(request)
    monkeypatch.setattr(runner._CheckedTransport, "__call__", checked)
    offline.handler = handler
    summary = batch()
    assert len(offline.requests) == 1 and len(callbacks) == 2
    native = {**callbacks[-1], "model": "qwen3.5-plus", "stream": False, "enable_thinking": False,
              "parallel_tool_calls": False, "temperature": 0, "max_tokens": 512,
              "response_format": {"type": "json_object"}}
    del native["tools"]
    assert len(encoded(native)) == 12289 and len(encoded(callbacks[-1])) < 12288
    result = read_json(offline.output / "RP01.json")["result"]
    assert result["inner"]["state"] == "failed" and summary["batch_passed"] is False
    assert len(result["audit"]["callback_entries"]) == result["inner"]["audit"]["downstream_calls"] == 2
    assert len(result["inner"]["served_evidence"]) == len(offline.tool_reads) == 1
    assert result["audit"]["callback_entries"][-1]["usable_read_ids"] == result["inner"]["audit"]["usable_read_ids"]
    assert result["audit"]["callback_exception_type"] == "CanaryStopped"
    assert summary["stop_reason"] == "request_too_large" and summary["unknown_usage_requests"] == 0


@pytest.mark.parametrize("kind", ["symlink", "reparse"])
@pytest.mark.parametrize("place", ["root", "source", "output"])
def test_indirect_paths_refuse_before_key(offline, monkeypatch, kind, place):
    """Disk/blob equality cannot authorize indirect source or output ancestors."""
    target = {"root": offline.repo, "source": offline.repo / runner.FIXTURE, "output": offline.output}[place]
    original = Path.lstat

    def lstat(path, *args, **kwargs):
        if path == target:
            return SimpleNamespace(st_mode=stat.S_IFLNK if kind == "symlink" else stat.S_IFREG,
                                   st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT if kind == "reparse" else 0)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(runner.CanaryStopped, match="indirect_path_rejected"):
        batch()
    assert not offline.key_reads and not offline.requests


@pytest.mark.parametrize("event,expected", [("manifest", 0), ("request_reserved", 0), ("request_finished", 1)])
def test_ledger_persistence_loss_preserves_pending_usage(offline, monkeypatch, event, expected):
    """Failed finish keeps observed usage in memory and its reservation pending."""
    original_append, original_open = RelationPolicyQwenLedger._append, Path.open
    original_init = RelationPolicyQwenLedger.__init__
    ledgers = []

    def init(self, *args, **kwargs):
        ledgers.append(self)
        original_init(self, *args, **kwargs)

    def append(self, row):
        if row["event"] == event:
            self.stop_reason = "persistence_failed"
            raise runner.CanaryStopped("persistence_failed")
        return original_append(self, row)

    def opened(path, mode="r", *args, **kwargs):
        if event == "manifest" and path == offline.output / "manifest.json":
            raise OSError("injected setup loss")
        return original_open(path, mode, *args, **kwargs)
    monkeypatch.setattr(RelationPolicyQwenLedger, "__init__", init)
    monkeypatch.setattr(RelationPolicyQwenLedger, "_append", append)
    monkeypatch.setattr(Path, "open", opened)
    if event == "manifest":
        with pytest.raises(runner.CanaryStopped):
            batch()
    else:
        result = batch()
        assert result["batch_passed"] is False
        if event == "request_finished":
            assert result["pending_request_id"] == 1 and result["unknown_usage_requests"] == 0
            assert ledgers[0].records[0]["reported_usage"] == USAGE
            assert not any(row["event"] == "request_finished" for row in events(offline.output))
    assert len(offline.requests) == expected


@contextmanager
def no_ambient_reads(monkeypatch, denied):
    """Guard provider credentials/configuration, not stdlib debug preferences.

    Match the frozen RP test contract: ordinary get returns its caller default
    without consulting the real mapping. Indexing/enumeration remain forbidden.
    The whole operation ends before pytest's reporter consults the environment.
    """
    class NoReads(dict):
        def get(self, name, default=None):
            if any(part in name for part in ("KEY", "QWEN", "PROXY")):
                denied.append(("get", name))
                raise AssertionError("ambient read")
            return default

        def __getitem__(self, key):
            denied.append(("index", key))
            raise AssertionError("ambient read")

        def items(self):
            denied.append(("items", None))
            raise AssertionError("ambient read")
    with monkeypatch.context() as scoped:
        scoped.setattr(os, "environ", NoReads())
        yield


@pytest.mark.parametrize("injected", [False, True])
def test_global_guard_ends_before_reporting(offline, monkeypatch, injected):
    """Construction/HTTP is guarded, even when failure escapes the guarded scope."""
    denied = []
    if injected:
        def handler(request):
            os.environ.get("DASHSCOPE_API_KEY")
            # Otherwise valid downstream replies ensure a missing guard cannot
            # pass merely because MockTransport later receives None/a bad reply.
            return provider(request)
        offline.handler = handler
    original_id = id(os.environ)
    with no_ambient_reads(monkeypatch, denied):
        result = batch()
    assert id(os.environ) == original_id
    assert shutil.get_terminal_size().columns > 0
    assert len(offline.requests) == (1 if injected else 6)
    assert result["batch_passed"] is (not injected)
    assert denied == ([("get", "DASHSCOPE_API_KEY")] if injected else [])
