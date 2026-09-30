"""Offline boundary controls, never native model-quality observations."""

from __future__ import annotations

import builtins
import ast
import copy
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
from types import CodeType
from concurrent.futures import ThreadPoolExecutor

import pytest

from evals.reviewer_comparison_v2 import runner as r
from evals.reviewer_comparison_v2 import credential as c
from evals.reviewer_comparison_v2 import source_loader as s


def secret(value="test-secret-only"):
    return c.parse_key(("DASHSCOPE_API_KEY=" + value).encode("ascii"))


@pytest.fixture(autouse=True)
def no_secrets_or_sockets(monkeypatch):
    def denied(*_args, **_kwargs):
        raise AssertionError("socket access forbidden in offline Reviewer tests")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)
    for module in (builtins, io):
        original = module.open

        def guarded(file, *args, _original=original, **kwargs):
            if isinstance(file, (str, os.PathLike)) and Path(file).name == ".env":
                raise AssertionError("real .env access forbidden")
            return _original(file, *args, **kwargs)

        monkeypatch.setattr(module, "open", guarded)


@pytest.fixture
def prepared():
    return r.prepare()


def envelope(content='{"corrections":[]}', **updates):
    payload = {"model": r.MODEL, "choices": [{"finish_reason": "stop", "message": {
        "role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 900, "completion_tokens": 40, "total_tokens": 940}}
    payload.update(updates)
    return payload


class FakeResponse:
    def __init__(self, body, status=200, headers=None):
        self.body, self.status_code = body, status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def iter_bytes(self, chunk_size):
        for start in range(0, len(self.body), chunk_size):
            yield self.body[start:start + chunk_size]


class FakeClient:
    def __init__(self, output, response=None, error=None, key="test-secret-only"):
        self.output = output
        self.response = response or FakeResponse(r.wire(envelope()))
        self.error = error
        self.key = key
        self.calls = []

    def stream(self, method, endpoint, **kwargs):
        journal = [json.loads(line) for line in (self.output / "journal.jsonl").read_text().splitlines()]
        assert journal[-1]["event"] == "reserved"
        assert journal[-1]["ordinal"] == len(self.calls) + 1
        assert journal[-1]["request_sha256"] == r.sha(kwargs["content"])
        assert method == "POST" and endpoint == r.ENDPOINT
        assert kwargs["headers"]["Authorization"] == "Bearer " + self.key
        self.calls.append(kwargs["content"])
        if self.error:
            raise self.error
        return self.response


def last_record(path):
    return json.loads((path / "journal.jsonl").read_text().splitlines()[-1])


def identity_process(mode, tmp_path, probe="none"):
    """Audit actual cold CLI/helpers through exit, not a replacement production()."""
    runtime = tmp_path / "dependency-runtime"
    runtime.mkdir()
    script = r'''
import atexit, os, pathlib, socket, sys
runtime = pathlib.Path(sys.argv[2]).resolve()
# Only ordinary interpreter/dependency temporary probes may use this boundary.
# Credential/configuration refusal is checked FIRST, even inside runtime.
for name in ("TEMP", "TMP", "TMPDIR"):
    os.environ[name] = str(runtime)
violations = []
counts = dict(framework=0, clients=0, network=0)
def forbidden(message):
    violations.append(message)
    raise AssertionError(message)
def safe_path(raw):
    path = pathlib.Path(os.path.abspath(os.fsdecode(raw)))
    if path.name.lower() in (".env", "secret.key", "tokens.enc", "settings.json",
                             "crewai_settings.json", ".crewai_write_test", ".crewai_user.json"):
        forbidden("credential or settings access")
    parts = [part.lower() for part in path.parts]
    if "credentials" in parts or any(parts[i:i+2] == [".config", "crewai"] for i in range(len(parts)-1)):
        forbidden("credential storage access")
    return path
def audit(event, args):
    if event == "import" and (args[0] in ("crewai", "crewai_core", "crewai_cli") or
                              args[0].startswith(("crewai.", "crewai_core.", "crewai_cli."))):
        counts["framework"] += 1
        forbidden("framework import forbidden")
    if event == "open":
        path, mode, flags = args
        if isinstance(path, (str, bytes, os.PathLike)):
            path = safe_path(path)
            writing = (mode and any(flag in mode for flag in "wax+")) or (
                flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            if writing and not path.is_relative_to(runtime):
                forbidden("identity artifact write")
    elif event == "os.mkdir":
        path = safe_path(args[0])
        if not path.is_relative_to(runtime):
            forbidden("identity artifact directory")
    elif event in ("socket.connect", "socket.getaddrinfo", "socket.gethostbyname",
                   "socket.gethostbyaddr", "socket.sendto"):
        counts["network"] += 1
        forbidden("network forbidden")
    elif event in ("os.listdir", "os.scandir", "os.remove", "os.rmdir"):
        if args and isinstance(args[0], (str, bytes, os.PathLike)):
            safe_path(args[0])
sys.addaudithook(audit)
# stat/access are not CPython audit events. Cover their actual OS wrappers too,
# without resolve()/exists() on protected paths and without framework stubs.
for name in ("stat", "lstat", "access"):
    original = getattr(os, name)
    def guarded(path, *args, _original=original, **kwargs):
        if isinstance(path, (str, bytes, os.PathLike)):
            safe_path(path)
        return _original(path, *args, **kwargs)
    setattr(os, name, guarded)
def exit_check():
    if violations or any(counts.values()):
        sys.stderr.write("AUDIT_FAILED " + repr(violations) + "\n")
        sys.stderr.flush()
        os._exit(87)
    sys.stderr.write("AUDIT_CLEAN framework=0 clients=0 network=0\n")
atexit.register(exit_check)
def denied(*a, **k):
    counts["network"] += 1
    forbidden("network forbidden")
socket.socket.connect = denied
socket.socket.connect_ex = denied
socket.create_connection = denied
socket.getaddrinfo = denied
# Fail at client construction even when a client would make no socket call.
import httpx
def no_client(*a, **k):
    counts["clients"] += 1
    forbidden("identity client creation")
httpx.Client.__init__ = no_client
httpx.AsyncClient.__init__ = no_client
from evals.reviewer_comparison_v2 import runner
assert "academic_agent.evidence" not in sys.modules
assert "crewai" not in sys.modules
environment = dict(os.environ)
probe = sys.argv[3]
if probe == "mkdir":
    runner.OUTPUT.mkdir()
elif probe == "os-mkdir":
    os.mkdir(runner.OUTPUT)
elif probe == "write":
    runner.OUTPUT.with_suffix(".json").write_bytes(b"synthetic")
elif probe == "os-open":
    os.open(runner.OUTPUT.with_suffix(".json"), os.O_WRONLY | os.O_CREAT)
elif probe == "client":
    runner.make_client()
elif probe == "credential":
    (runner.ROOT / ".env").read_bytes()
elif probe == "dependency-credential":
    (runtime / "secret.key").read_bytes()
elif probe == "credential-storage":
    (runtime / "crewai" / "credentials").mkdir()
elif probe == "settings":
    (runtime / "crewai_settings.json").read_bytes()
elif probe == "settings-probe":
    (runtime / "settings.json").is_file()
elif probe == "consent":
    (runtime / ".crewai_user.json").read_bytes()
elif probe == "tokens":
    os.open(runtime / "tokens.enc", os.O_RDONLY)
elif probe == "framework-import":
    __import__("crewai")
elif probe == "socket":
    socket.create_connection(("example.invalid", 443))
elif probe == "dns":
    socket.getaddrinfo("example.invalid", 443)
if sys.argv[1] == "identity":
    assert runner.main([]) == 0, violations
elif sys.argv[1] == "production":
    assert runner.production()["EvidenceReport"].__module__.startswith("reviewer_comparison_v2.source_locked_")
elif sys.argv[1] == "prepare":
    assert len(runner.prepare()["requests"]) == 6
elif sys.argv[1] == "repeat":
    first = runner.prepare()
    assert runner.prepare()["identity"] == first["identity"]
assert violations == [], violations
assert dict(os.environ) == environment
assert not any(name == "crewai" or name.startswith(("crewai.", "crewai_core")) for name in sys.modules)
assert "academic_agent.evidence" not in sys.modules
'''
    return subprocess.run([sys.executable, "-B", "-c", script, mode,
                           str(runtime), probe], cwd=r.ROOT,
                          capture_output=True, text=True, timeout=120)


@pytest.mark.parametrize("mode", ("import", "identity", "production", "prepare", "repeat"))
def test_default_import_and_cli_do_not_read_credentials_or_connect(mode, tmp_path):
    """Cold extraction never imports framework or admits config as a cache."""
    result = identity_process(mode, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    if mode == "identity":
        value = json.loads(result.stdout)
        assert value["mode"] == "identity_only" and value["live_authorized"] is False
        assert "DASHSCOPE_API_KEY" not in result.stdout
    assert list((tmp_path / "dependency-runtime").iterdir()) == []
    assert "AUDIT_CLEAN framework=0 clients=0 network=0" in result.stderr


@pytest.mark.parametrize(("probe", "error"), (
    ("mkdir", "identity artifact directory"),
    ("os-mkdir", "identity artifact directory"),
    ("write", "identity artifact write"),
    ("os-open", "identity artifact write"),
    ("client", "identity client creation"),
    ("credential", "credential or settings access"),
    ("dependency-credential", "credential or settings access"),
    ("credential-storage", "credential storage access"),
    ("dns", "network forbidden"),
    ("socket", "network forbidden"),
    ("settings", "credential or settings access"),
    ("settings-probe", "credential or settings access"),
    ("consent", "credential or settings access"),
    ("tokens", "credential or settings access"),
    ("framework-import", "framework import forbidden"),
))
def test_fresh_identity_guards_reject_forbidden_seams(tmp_path, probe, error):
    """Negative controls reject actual writes, claims, clients and secret/network I/O."""
    result = identity_process("import", tmp_path, probe)
    assert result.returncode != 0
    assert "AssertionError: " + error in result.stderr
    assert "AUDIT_FAILED" in result.stderr
    assert list((tmp_path / "dependency-runtime").iterdir()) == []


@pytest.mark.parametrize("drift", ("none", "source", "requests", "dependency", "wrong-helper", "missing-history"))
def test_frozen_instructions_paired_context_and_identity_drift(prepared, monkeypatch, drift):
    """Reject a changed source/body/dependency, not merely malformed hashes."""
    if drift == "source":
        original = r.source_bytes
        monkeypatch.setattr(r, "source_bytes", lambda path: original(path) + b" ")
    elif drift == "requests":
        original = r.render_request
        monkeypatch.setattr(r, "render_request", lambda *args: original(*args) + b" ")
    elif drift == "dependency":
        monkeypatch.setattr(r.importlib.metadata, "version", lambda _name: "0.invalid")
    elif drift == "wrong-helper":
        r.production()
        monkeypatch.setitem(s._CACHE["evidence"][0], "validate_final_report", lambda *_args: [])
        with pytest.raises(r.Fault, match="derived_binding_drift"):
            r.production()
        return
    elif drift == "missing-history":
        def unavailable(*_args):
            raise r.Fault("git_identity_unavailable")

        monkeypatch.setattr(r, "git", unavailable)
        with pytest.raises(r.Fault, match="git_identity_unavailable"):
            r.verify_historical_roots(prepared["manifest"])
        return
    if drift != "none":
        with pytest.raises(r.Fault, match="drift"):
            r.prepare()
        return
    for first in (0, 2, 4):
        pair = [json.loads(body) for body in prepared["requests"][first:first + 2]]
        contexts = [item["messages"][1]["content"].split("Untrusted supplied context JSON:\n")[1] for item in pair]
        assert contexts[0] == contexts[1]
        assert pair[0]["messages"][0] != pair[1]["messages"][0]
        reports = json.loads(contexts[0])["evidence_reports"]
        assert len(reports) == 3 and all(report["sources"] and report["findings"] for report in reports)
    for arm in prepared["manifest"]["arms"].values():
        assert all(word in arm["agent"]["block"] for word in ("role:", "goal:", "backstory:", "Rule 7"))
        assert all(word in arm["task"]["block"] for word in ("description:", "expected_output:", "agent:"))
    assert r.RESERVE == r.Decimal("0.014548032")
    assert all(len(body) <= r.MAX_REQUEST_BYTES for body in prepared["requests"])


@pytest.mark.parametrize("fault", ("commit", "identity", "ci", "dirty", "uncommitted", "occupied", "missing-history"))
def test_live_identity_gate_refuses_before_key_or_post(prepared, monkeypatch, tmp_path, fault):
    """Live never consumes a key before committed identities and CI attestation."""
    output = tmp_path / "fixed"
    monkeypatch.setattr(r, "OUTPUT", output)
    monkeypatch.setattr(r, "_read_key", lambda: pytest.fail("key reached before gate"))
    monkeypatch.setattr(r, "make_client", lambda: pytest.fail("HTTP client reached before gate"))
    commit, identity, ci = prepared["facts"]["commit"], prepared["identity"], prepared["facts"]["commit"]

    def fake_git(*args):
        if args[0] == "rev-parse":
            return prepared["facts"]["commit"].encode()
        if args[0] == "status":
            return b" M changed" if fault == "dirty" else b""
        if args[0] == "show":
            if not args[1].startswith("HEAD:"):
                raise r.Fault("git_identity_unavailable")
            return b"different" if fault == "uncommitted" else r.source_bytes(args[1].split(":", 1)[1])
        raise AssertionError(args)

    monkeypatch.setattr(r, "git", fake_git)
    if fault == "commit":
        commit = "0" * 40
    if fault == "identity":
        identity = "0" * 64
    if fault == "ci":
        ci = None
    if fault == "occupied":
        output.mkdir()
    with pytest.raises(r.Fault):
        r.run_live(prepared, commit, identity, ci)
    if fault == "missing-history":
        assert not output.exists(), "missing historical roots must precede the output claim"


@pytest.mark.parametrize("point", ("request", "reservation", "response"))
def test_persistence_fault_never_dispatches_or_continues(prepared, monkeypatch, tmp_path, point):
    """A failed request/reservation fsync causes zero POSTs; later faults stop."""
    calls = 0
    original = r.os.fsync
    target = {"request": 1, "reservation": 2, "response": 3}[point]

    def fsync(fd):
        nonlocal calls
        calls += 1
        if calls == target:
            raise OSError("synthetic fsync fault")
        return original(fd)

    monkeypatch.setattr(r.os, "fsync", fsync)
    client = FakeClient(tmp_path)
    with pytest.raises((OSError, r.Fault)):
        r._execute(prepared, tmp_path, client, secret())
    assert len(client.calls) == (1 if point == "response" else 0)
    if point == "response":
        assert last_record(tmp_path)["usage"]["status"] == "known"


def test_six_sequential_calls_keep_reservations_and_blind_final_text(prepared, monkeypatch, tmp_path):
    """Mechanically valid bad no-op answers still finish all six, without gain."""
    syncs = []
    original = r.os.fsync
    monkeypatch.setattr(r.os, "fsync", lambda fd: (syncs.append(fd), original(fd))[-1])
    client = FakeClient(tmp_path)
    result = r._execute(prepared, tmp_path, client, secret())
    assert client.calls == prepared["requests"] and len(client.calls) == 6
    assert result["mechanically_complete"] == 6 and result["semantic_review"] == "not_run"
    assert result["gain"] == "unassessed" and "passed" not in result
    assert len(syncs) >= 6 * 7
    for index in range(1, 7):
        prefix = tmp_path / f"{index:02d}"
        packet = json.loads(prefix.with_suffix(".blind.json").read_text())
        delivery = json.loads(prefix.with_suffix(".delivery.json").read_text())
        assert set(packet) == {"source_text", "original_draft", "actual_final", "rubric"}
        assert packet["actual_final"] == prefix.with_suffix(".final.md").read_text()
        assert packet["actual_final"] == packet["original_draft"].strip()
        assert delivery["applied_reasons"] == [] and delivery["unapplied_corrections"] == []
        assert delivery["applied_corrections"] == 0
    # Reusing the same files cannot issue another request even through the loop.
    with pytest.raises(FileExistsError):
        r._execute(prepared, tmp_path, client, secret())
    assert len(client.calls) == 6


def test_endpoint_tls_and_environment_independent_client(prepared, monkeypatch, tmp_path):
    """Ambient model/base/proxy/CA values cannot select the paid destination."""
    import httpx

    seen = {}
    for name in ("QWEN_MODEL", "QWEN_API_BASE", "OPENAI_BASE_URL", "HTTP_PROXY", "SSL_CERT_FILE"):
        monkeypatch.setenv(name, "https://untrusted.invalid")
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **kwargs: seen.setdefault("transport", kwargs))
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: seen.setdefault("client", kwargs))
    r.make_client()
    assert seen["transport"] == {"retries": 0, "verify": True, "trust_env": False}
    assert seen["client"]["follow_redirects"] is False
    assert seen["client"]["trust_env"] is False and seen["client"]["verify"] is True
    assert seen["client"]["timeout"].connect == 10
    body = json.loads(prepared["requests"][0])
    assert body["model"] == "qwen3.5-plus" and body["enable_thinking"] is False
    assert body["response_format"] == {"type": "json_object"} and body["temperature"] == 0
    assert body["max_tokens"] == 1500 and "tools" not in body


@pytest.mark.parametrize("fault", ("redirect", "status", "timeout", "model", "malformed", "echo",
                                  "escaped-echo", "nested-echo", "key-echo", "malformed-echo"))
def test_transport_faults_stop_without_retry_preserving_known_usage(prepared, tmp_path, fault):
    """Model/content/status failures keep already observed usage and stop."""
    import httpx

    payload = envelope()
    status, error = 200, None
    if fault == "redirect":
        status = 307
    if fault == "status":
        status = 503
    if fault == "timeout":
        error = httpx.ReadTimeout("must not expose test-secret-only")
    if fault == "model":
        payload["model"] = "unrequested-model"
    if fault == "malformed":
        payload["choices"][0]["message"]["content"] = "{"
    if fault == "echo":
        payload["choices"][0]["message"]["content"] = "test-secret-only"
    encoded_key = "".join(f"\\u{ord(char):04x}" for char in "test-secret-only")
    if fault == "nested-echo":
        payload["choices"][0]["message"]["content"] = '{"nested":"' + encoded_key + '"}'
    if fault == "key-echo":
        payload["extra"] = {encoded_key: "untrusted"}
    body = r.wire(payload)
    if fault == "escaped-echo":
        body = body.replace(b'"content":"{\\"corrections\\":[]}"', b'"content":"' + encoded_key.encode() + b'"')
        assert encoded_key.encode() in body and b"test-secret-only" not in body
    if fault == "malformed-echo":
        body = b'{"secret":"' + encoded_key.encode()
    client = FakeClient(tmp_path, FakeResponse(body, status), error)
    with pytest.raises(r.Fault) as raised:
        r._execute(prepared, tmp_path, client, secret())
    assert len(client.calls) == 1 and "test-secret-only" not in str(raised.value)
    usage = last_record(tmp_path)["usage"]
    assert usage["status"] == ("unknown" if fault in ("timeout", "malformed-echo") else "known")
    if fault not in ("timeout", "malformed-echo"):
        assert usage["input_tokens"] == 900 and r.Decimal(usage["usd_estimate"]) > 0
    if "echo" in fault:
        assert not list(tmp_path.glob("*.response.json"))
        assert not list(tmp_path.glob("*.model.txt"))
        assert not list(tmp_path.glob("*.delivery.json"))
        for path in tmp_path.iterdir():
            assert b"test-secret-only" not in path.read_bytes()
            assert encoded_key.encode() not in path.read_bytes()
            assert r.sha(body).encode() not in path.read_bytes()
            assert r.sha(b"test-secret-only").encode() not in path.read_bytes()
        assert last_record(tmp_path)["response_sha256"] is None


@pytest.mark.parametrize("fault", ("bytes", "truncated", "envelope", "encoding", "duplicate",
                                  "21-edits", "long-find", "long-reason", "long-replace"))
def test_response_and_strict_patch_bounds_have_no_repair(prepared, tmp_path, fault):
    """Full response, finish reason and actual Pydantic correction bounds apply."""
    payload = envelope()
    headers = {}
    edit = {"find": "absent", "replace": "replacement", "reason": "reason"}
    if fault == "truncated":
        payload["choices"][0]["finish_reason"] = "length"
    if fault == "encoding":
        headers = {"content-encoding": "gzip"}
    if fault == "duplicate":
        payload["choices"][0]["message"]["content"] = '{"corrections":[],"corrections":[]}'
    if fault == "21-edits":
        payload["choices"][0]["message"]["content"] = json.dumps({"corrections": [edit] * 21})
    for key in ("find", "reason", "replace"):
        if fault == "long-" + key:
            edit[key] = "x" * (301 if key == "reason" else 2001)
            payload["choices"][0]["message"]["content"] = json.dumps({"corrections": [edit]})
    body = r.wire(payload)
    if fault == "bytes":
        body = b" " * (r.MAX_RESPONSE_BYTES + 1)
    if fault == "envelope":
        body = b"{"
    client = FakeClient(tmp_path, FakeResponse(body, headers=headers))
    with pytest.raises(r.Fault):
        r._execute(prepared, tmp_path, client, secret())
    assert len(client.calls) == 1


@pytest.mark.parametrize("usage", (None, {}, {"prompt_tokens": True, "completion_tokens": 2, "total_tokens": 3},
                                  {"prompt_tokens": 100, "completion_tokens": 2, "total_tokens": 4},
                                  {"prompt_tokens": 16385, "completion_tokens": 2, "total_tokens": 16387},
                                  {"prompt_tokens": 100, "completion_tokens": 1501, "total_tokens": 1601}))
def test_unknown_usage_is_not_zero_and_overflow_stops(prepared, tmp_path, usage):
    """Missing/inconsistent counts cannot refund reservations or become free."""
    client = FakeClient(tmp_path, FakeResponse(r.wire(envelope(usage=usage))))
    with pytest.raises(r.Fault, match="unknown_usage|usage_overflow"):
        r._execute(prepared, tmp_path, client, secret())
    assert len(client.calls) == 1
    saved = last_record(tmp_path)["usage"]
    if saved["status"] == "unknown":
        assert saved["usd_estimate"] is None and saved["input_tokens"] is None
    else:
        assert saved["input_tokens"] > r.INPUT_RESERVE or saved["output_tokens"] > r.MAX_OUTPUT


@pytest.mark.parametrize("fault", ("budget", "seven", "request-drift"))
def test_budget_call_count_and_exact_request_prechecks(prepared, monkeypatch, tmp_path, fault):
    """Admission bounds reject oversubscription or an injected body before POST."""
    prepared = copy.deepcopy(prepared)
    if fault == "budget":
        monkeypatch.setattr(r, "BUDGET", r.Decimal("0.01"))
    elif fault == "seven":
        prepared["requests"].append(prepared["requests"][0])
    else:
        prepared["requests"][0] += b" "
    client = FakeClient(tmp_path)
    with pytest.raises(r.Fault):
        r._execute(prepared, tmp_path, client, secret())
    assert client.calls == []


@pytest.mark.parametrize("control", ("partial", "ambiguous", "heading", "noop", "edit", "citation", "shrink"))
def test_real_patch_and_validator_controls(prepared, control):
    """Actual patch seam: partial is not success; no-ops count zero applied."""
    case = copy.deepcopy(prepared["cases"][0])
    old = "The pressure monitor had a calibration error of 13.7 kPa in the fixed-blower trial [A1]."
    new = "At the fixed blower setting, loading the filter raised duct pressure by 13.7 kPa relative to bypass; calibration error was not established [A1]."
    edits = [{"find": old, "replace": new, "reason": "Correct the compared physical conditions."}]
    if control == "partial":
        edits.append({"find": "missing target", "replace": "changed", "reason": "A required dependent correction."})
    elif control == "ambiguous":
        edits[0]["find"] = "[A1]"
    elif control == "heading":
        edits[0]["find"] = "## Executive Summary"
    elif control == "noop":
        edits[0]["replace"] = old
    elif control == "citation":
        edits[0]["replace"] = "A new unsupported measurement is 12 [A99]."
    elif control == "shrink":
        # Keep headings/cites but strip enough prose to trip the independent 80% check.
        edits = [{"find": line, "replace": "[M1]", "reason": "Synthetic deletion control."}
                 for line in case["draft"].splitlines() if len(line) > 100 and "[M1]" in line]
        case["draft"] = case["draft"].replace("## Evidence Limitations", "Padding " * 100 + "[A1]\n\n## Evidence Limitations")
        edits.append({"find": "Padding " * 100 + "[A1]", "replace": "[A1]", "reason": "Synthetic deletion control."})
    raw = json.dumps({"corrections": edits})
    result = r.apply_plan(raw, case)
    assert result["complete"] is (control in ("noop", "edit"))
    if control == "partial":
        assert new in result["final_text"] and result["unapplied_corrections"]
    if control == "noop":
        assert result["applied_reasons"] == [] and result["final_text"] == case["draft"].strip()
    if control == "edit":
        assert new in result["final_text"] and len(result["applied_reasons"]) == 1
        # Correct application is not a semantic verdict: the dependent error remains.
        assert "deployment requires a 1.37 kPa" in result["final_text"]
    if control == "shrink":
        assert "length_regression" in result["errors"]


@pytest.mark.parametrize("key_text,valid", (
    (b"OTHER_KEY=do-not-use\nDASHSCOPE_API_KEY=sk-synthetic-key123\n", True),
    (b"export DASHSCOPE_API_KEY='sk-synthetic-key123'\n", True),
    (b"DASHSCOPE_API_KEY=sk-synthetic-key123\nDASHSCOPE_API_KEY=sk-duplicate-key\n", False),
    (b"DASHSCOPE_API_KEY=sk-synthetic\x00-key", False),
    (b"DASHSCOPE_API_KEY=sk-synthetic\x7f-key", False),
    (b"DASHSCOPE_API_KEY=sk-synthetic key", False),
    (b"DASHSCOPE_API_KEY=${OTHER_KEY}", False),
    (b"DASHSCOPE_API_KEY='sk-unclosed-key", False),
    (b"OPENAI_API_KEY=sk-other-synthetic-key", False),
))
def test_narrow_key_parser_with_synthetic_bytes_only(key_text, valid):
    """No inherited provider choice, duplicate assignment, expansion or controls."""
    if valid:
        assert c.parse_key(key_text).authorization() == "Bearer sk-synthetic-key123"
    else:
        with pytest.raises(c.CredentialError):
            c.parse_key(key_text)


def admit_test_gate(prepared, monkeypatch, output):
    """Only local Git/fixture seams are replaced; real native ordering remains."""
    monkeypatch.setattr(r, "OUTPUT", output)

    def fake_git(*args):
        if args == ("rev-parse", "HEAD"):
            return prepared["facts"]["commit"].encode()
        if args[0] == "status":
            return b""
        if args[0] == "show" and args[1].startswith("HEAD:"):
            return r.source_bytes(args[1].split(":", 1)[1])
        raise AssertionError(args)

    monkeypatch.setattr(r, "git", fake_git)
    monkeypatch.setattr(r, "verify_historical_roots", lambda _manifest: None)
    return (prepared["facts"]["commit"], prepared["identity"], prepared["facts"]["commit"])


@pytest.mark.parametrize("token", (
    "ABCDEFGHIJ", "0123456789", "1234567890", "a" * 256, "A-._~+/z09==", "abcde12345=====",
    "sk-synthetic.Key/~+with_padding==", "abc.def_ghi-jkl~mno+pqr/stu=",
))
@pytest.mark.parametrize("quote", ("", "'", '"'))
def test_complete_bearer_bytes_cross_actual_httpx_boundary(token, quote):
    """Punctuation/padding survive the parser AND actual HTTP header serializer."""
    import httpx

    key = c.parse_key(("DASHSCOPE_API_KEY=" + quote + token + quote + "\r\n").encode())
    seen = []

    def handler(request):
        assert request.method == "POST" and str(request.url) == r.ENDPOINT
        assert request.headers.raw.count((b"Authorization", b"Bearer " + token.encode())) == 1
        assert request.content == b'{"synthetic":true}'
        seen.append(request)
        return httpx.Response(200, content=b"{}")

    with httpx.Client(transport=httpx.MockTransport(handler), trust_env=False) as client:
        assert r.receive(client, key, b'{"synthetic":true}') == (200, b"{}")
    assert len(seen) == 1
    assert token not in repr(key) and token not in str(key)


@pytest.mark.parametrize("value", (
    "", "short", "x" * 257, "a" * 9, "=abcdefghij", "abc=defghij", "abcde=12345=",
    "abcdefghij ", " abcdefghij", "abcde fghij", "abcdefghij#comment",
    "abcdefghij #comment", "'abcdefghij", '"abcdefghij', "'abcdefghij\"",
    "' abcdefghij'", '"abcdefghij "', '"abcdefghij" extra', "'abcdefghij'#comment",
    "${OTHER_KEY}", "$OTHER_KEY", "$(echo fake)", "`abcdefghij`",
    "abcde\\fghij", '"abcde\\u0066ghij"', "abcde...fghij", "abcde***fghij",
    "abcde…fghij", "abcdé-fghij", "abcdefghij\r", "abcdefghij\x85", "abcdefghij\u2028",
))
def test_selected_rhs_is_literal_never_repaired(value):
    """No trim, unescape, whitespace/control removal, reference or mask repair."""
    with pytest.raises(c.CredentialError) as raised:
        c.parse_key(("DASHSCOPE_API_KEY=" + value).encode("utf-8"))
    assert str(raised.value) == "credential_preflight_failed"


@pytest.mark.parametrize("control", tuple(range(32)) + (127,))
def test_selected_control_bytes_cannot_split_or_normalize_a_key(control):
    """Every ASCII control, including splitlines-only separators, fails closed."""
    raw = b'DASHSCOPE_API_KEY="abcde' + bytes([control]) + b'fghij"'
    with pytest.raises(c.CredentialError):
        c.parse_key(raw)


@pytest.mark.parametrize("raw", (
    b"OTHER=DASHSCOPE_API_KEY\nDASHSCOPE_API_KEY=abcdefghij",
    b"OTHER='unterminated DASHSCOPE_API_KEY=${ignored}\nDASHSCOPE_API_KEY=abcdefghij",
    b"DASHSCOPE_API_KEY_OTHER=not-the-key\nDASHSCOPE_API_KEY=abcdefghij",
    b"# DASHSCOPE_API_KEY=ignored\r\nDASHSCOPE_API_KEY=abcdefghij\r\n",
    b"\xef\xbb\xbfexport DASHSCOPE_API_KEY='abcdefghij'\r\n",
    b'\t export\tDASHSCOPE_API_KEY\t="abcdefghij"\n',
    b"OTHER=ignored\x0bDASHSCOPE_API_KEY=not-selected\nDASHSCOPE_API_KEY=abcdefghij",
    b"OTHER=ignored\rDASHSCOPE_API_KEY=not-selected\nDASHSCOPE_API_KEY=abcdefghij",
))
def test_exact_lhs_selection_ignores_other_values_without_parsing(raw):
    """Mentions/invalid quotes elsewhere do not select or invalidate a credential."""
    assert c.parse_key(raw).authorization() == "Bearer abcdefghij"


@pytest.mark.parametrize("raw", (
    b"OTHER=DASHSCOPE_API_KEY=abcdefghij", b"DASHSCOPE_API_KEY_OTHER=abcdefghij",
    b"DASHSCOPE_API_KEY:abcdefghij", b"DASHSCOPE_API_KEY abcdefghij",
    b"DASHSCOPE_API_KEY==abcdefghij", b"DASHSCOPE_API_KEY=abcdefghij\rDASHSCOPE_API_KEY=klmnopqrst",
    b"DASHSCOPE_API_KEY=abcdefghij\nexport DASHSCOPE_API_KEY=klmnopqrst",
    b"DASHSCOPE_API_KEY=abcdefghij\nDASHSCOPE_API_KEY=",
    b"DASHSCOPE_API_KEY=\nDASHSCOPE_API_KEY=abcdefghij",
    b"\xef\xbb\xbf\xef\xbb\xbfDASHSCOPE_API_KEY=abcdefghij",
    b"# initial line\n\xef\xbb\xbfDASHSCOPE_API_KEY=abcdefghij",
    b"DASHSCOPE_API_KEY=abcdefghij\nOTHER=\xef\xbb\xbf",
    b"DASHSCOPE_API_KEY=abcdefghij\xff",
    b"OTHER=ignored\x0bDASHSCOPE_API_KEY=abcdefghij",
))
def test_physical_lines_bom_duplicates_and_malformed_selection(raw):
    """BOM is file-initial only; only LF/CRLF delimit assignments."""
    with pytest.raises(c.CredentialError):
        c.parse_key(raw)


@pytest.mark.parametrize("variant", ("valid", "missing", "oversize", "unreadable"))
def test_fixed_file_read_bound_no_environment_fallback(monkeypatch, variant):
    """Ambient valid keys never repair failed fixed-path literal admission."""
    token = "fake.local/~+credential=="
    for name in ("DASHSCOPE_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "DOTENV_PATH"):
        monkeypatch.setenv(name, token)
    data = b"DASHSCOPE_API_KEY=abcdefghij\n"
    if variant == "missing":
        data = b"OTHER=abcdefghij\n"
    if variant == "oversize":
        data += b"#" * c.MAX_FILE_BYTES
    calls = []

    class BoundedBytes(io.BytesIO):
        def read(self, size=-1):
            assert size == 65537
            calls.append("read")
            return super().read(size)

    def fake_open(path, mode):
        assert path == c.ROOT / ".env" and mode == "rb"
        calls.append("open")
        if variant == "unreadable":
            raise OSError(token)
        return BoundedBytes(data)

    with monkeypatch.context() as local:
        local.setattr(Path, "open", fake_open)
        if variant == "valid":
            assert c.read_key().authorization() == "Bearer abcdefghij"
        else:
            with pytest.raises(c.CredentialError) as raised:
                c.read_key()
            assert str(raised.value) == "credential_preflight_failed"
    assert calls == (["open"] if variant == "unreadable" else ["open", "read"])


def test_exact_file_byte_bound_and_secret_representation():
    """The selected token is never hashed, serialized or included in repr."""
    import pickle

    raw = b"DASHSCOPE_API_KEY=abcdefghij\n"
    key = c.parse_key(raw + b"#" * (c.MAX_FILE_BYTES - len(raw)))
    assert str(key) == repr(key) == "SecretKey(<redacted>)"
    assert "abcdefghij" not in repr({"key": key})
    with pytest.raises(TypeError, match="credential_serialization_forbidden"):
        pickle.dumps(key)
    with pytest.raises(TypeError):
        r.wire(key)
    with pytest.raises(c.CredentialError):
        c.parse_key(raw + b"#" * (c.MAX_FILE_BYTES - len(raw) + 1))


@pytest.mark.parametrize("outcome", ("success", "credential", "gate", "local"))
def test_explicit_preflight_fixed_stdout_no_client_or_artifacts(prepared, monkeypatch, tmp_path, capsys, outcome):
    """Explicit syntax mode neither claims a batch nor leaks failure categories."""
    output = tmp_path / "fixed"
    args = admit_test_gate(prepared, monkeypatch, output)
    key = secret("fake.local/~+credential==")
    reads = []
    prepares = []

    def read():
        reads.append(True)
        if outcome == "credential":
            raise c.CredentialError()
        if outcome == "local":
            raise OSError(key.authorization())
        return key

    def prepare():
        prepares.append(True)
        return prepared

    monkeypatch.setattr(r, "prepare", prepare)
    monkeypatch.setattr(r, "_read_key", read)
    monkeypatch.setattr(r, "make_client", lambda: pytest.fail("preflight created client"))
    monkeypatch.setattr(r, "persist", lambda *_args: pytest.fail("preflight wrote artifact"))
    monkeypatch.setattr(r, "append", lambda *_args: pytest.fail("preflight wrote journal"))
    commit, identity, ci = args
    if outcome == "gate":
        ci = "0" * 40
    result = r.main(["--credential-preflight", "--expected-commit", commit,
                     "--expected-identity", identity, "--reviewed-ci-commit", ci])
    assert result == (0 if outcome == "success" else 1)
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "status": "syntax_admitted" if outcome == "success" else "credential_preflight_failed",
        "provider_authentication": "not_checked",
    }
    assert reads == ([] if outcome == "gate" else [True])
    assert len(prepares) == (2 if outcome == "success" else 1)
    assert not output.exists() and list(tmp_path.iterdir()) == []
    assert "fake.local" not in captured.out
    assert r.sha(b"fake.local/~+credential==") not in captured.out


@pytest.mark.parametrize("mode", ("--live", "--credential-preflight"))
def test_cli_requires_gate_before_selected_read(prepared, monkeypatch, tmp_path, capsys, mode):
    """Presence of a paid/syntax flag alone cannot grant identity or CI authority."""
    monkeypatch.setattr(r, "prepare", lambda: prepared)
    monkeypatch.setattr(r, "OUTPUT", tmp_path / "fixed")
    monkeypatch.setattr(r, "_read_key", lambda: pytest.fail("ungated credential read"))
    monkeypatch.setattr(r, "make_client", lambda: pytest.fail("ungated client"))
    assert r.main([mode]) == 1
    captured = capsys.readouterr()
    if mode == "--credential-preflight":
        assert "not_checked" in captured.out
    assert not r.OUTPUT.exists()


def test_cli_modes_are_mutually_exclusive_before_preparation(monkeypatch):
    """Conflicting intent is refused by argparse before any work or key read."""
    monkeypatch.setattr(r, "prepare", lambda: pytest.fail("conflicting modes reached preparation"))
    with pytest.raises(SystemExit) as raised:
        r.main(["--live", "--credential-preflight"])
    assert raised.value.code == 2


def test_credential_failure_precedes_claim_and_client(prepared, monkeypatch, tmp_path):
    """The v1 early-claim defect must leave no output on credential rejection."""
    output = tmp_path / "fixed"
    args = admit_test_gate(prepared, monkeypatch, output)

    def fail_key():
        assert not output.exists()
        raise c.CredentialError()

    monkeypatch.setattr(r, "_read_key", fail_key)
    monkeypatch.setattr(r, "make_client", lambda: pytest.fail("failed credential reached client"))
    with pytest.raises(c.CredentialError):
        r.run_live(prepared, *args)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("drift", ("source", "commit", "dependency", "requests"))
def test_identity_drift_during_key_read_precedes_claim_client(prepared, monkeypatch, tmp_path, drift):
    """Real preparation is repeated after the key read, not a stale-object check."""
    output = tmp_path / "fixed"
    args = admit_test_gate(prepared, monkeypatch, output)
    reads = []

    def read():
        reads.append(True)
        if drift == "source":
            original = r.source_bytes
            monkeypatch.setattr(r, "source_bytes", lambda path: original(path) + b" ")
        if drift == "dependency":
            monkeypatch.setattr(r.importlib.metadata, "version", lambda _name: "drift")
        if drift == "requests":
            original = r.render_request
            monkeypatch.setattr(r, "render_request", lambda *args: original(*args) + b" ")
        if drift == "commit":
            original = r.git
            monkeypatch.setattr(r, "git", lambda *args: b"0" * 40 if args == ("rev-parse", "HEAD") else original(*args))
        return secret()

    monkeypatch.setattr(r, "_read_key", read)
    monkeypatch.setattr(r, "make_client", lambda: pytest.fail("drift reached client"))
    with pytest.raises(r.Fault):
        r.run_live(prepared, *args)
    assert reads == [True] and list(tmp_path.iterdir()) == []


def test_preflight_is_not_native_ticket_and_live_uses_same_key(prepared, monkeypatch, tmp_path):
    """Native rereads independently of syntax mode, once, with no later fallback."""
    output = tmp_path / "fixed"
    args = admit_test_gate(prepared, monkeypatch, output)
    keys = [secret("first.preflight/key=="), secret("native.same/~+key==")]
    reads, clients, syncs = [], [], []
    original_sync = r.os.fsync
    monkeypatch.setattr(r.os, "fsync", lambda fd: (syncs.append(fd), original_sync(fd))[-1])

    def read():
        assert not output.exists()
        reads.append(True)
        return keys[len(reads) - 1]

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def client():
        assert len(syncs) >= 3 and last_record(output)["event"] == "claimed"
        assert (output / "identity.json").is_file() and (output / "manifest.json").is_file()
        clients.append(True)
        return Client()

    def execute(actual, fixed_output, _client, key):
        assert actual["identity"] == prepared["identity"] and fixed_output == output
        assert key is keys[1] and key.authorization() == "Bearer native.same/~+key=="
        assert len(reads) == 2
        return {"synthetic": True}

    monkeypatch.setattr(r, "_read_key", read)
    monkeypatch.setattr(r, "make_client", client)
    monkeypatch.setattr(r, "_execute", execute)
    assert r.credential_preflight(prepared, *args)["status"] == "syntax_admitted"
    assert not output.exists() and not clients
    assert r.run_live(prepared, *args) == {"synthetic": True}
    assert reads == [True, True] and clients == [True]
    with pytest.raises(r.Fault, match="occupied_output"):
        r.run_live(prepared, *args)
    assert len(reads) == 2 and len(clients) == 1


@pytest.mark.parametrize("point", ("identity", "manifest", "claim", "client", "execute", "summary"))
def test_postclaim_fault_stays_occupied_no_reread_fallback_or_redispatch(prepared, monkeypatch, tmp_path, point):
    """Every postclaim failure closes this batch, even before the first POST."""
    output = tmp_path / "fixed"
    args = admit_test_gate(prepared, monkeypatch, output)
    reads, clients, executions = [], [], []
    monkeypatch.setattr(r, "_read_key", lambda: (reads.append(True), secret())[-1])
    original_persist, original_append = r.persist, r.append

    def persist(path, data):
        if path.name == point + ".json":
            raise OSError("synthetic persistence fault")
        return original_persist(path, data)

    def append(path, record):
        if point == "claim" and record["event"] == "claimed":
            raise OSError("synthetic claim fsync fault")
        return original_append(path, record)

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def client():
        clients.append(True)
        if point == "client":
            raise OSError("synthetic client fault")
        return Client()

    def execute(*_args):
        executions.append(True)
        if point == "execute":
            raise r.Fault("synthetic_execution_fault")
        return {"synthetic": True}

    monkeypatch.setattr(r, "persist", persist)
    monkeypatch.setattr(r, "append", append)
    monkeypatch.setattr(r, "make_client", client)
    monkeypatch.setattr(r, "_execute", execute)
    with pytest.raises((r.Fault, OSError)):
        r.run_live(prepared, *args)
    assert output.is_dir() and reads == [True]
    assert len(clients) == (1 if point in ("client", "execute", "summary") else 0)
    assert len(executions) == (1 if point in ("execute", "summary") else 0)
    state = (len(reads), len(clients), len(executions))
    with pytest.raises(r.Fault, match="occupied_output"):
        r.run_live(prepared, *args)
    assert state == (len(reads), len(clients), len(executions))


def test_two_native_claim_racers_only_one_client(prepared, monkeypatch, tmp_path):
    """Both racers pass both gates before mkdir; only its winner gets a client."""
    output = tmp_path / "fixed"
    args = admit_test_gate(prepared, monkeypatch, output)
    barrier = threading.Barrier(2, timeout=15)
    local = threading.local()
    clients, reads = [], []
    gate = r.live_gate

    def synchronized_gate(*args):
        gate(*args)
        local.gates = getattr(local, "gates", 0) + 1
        if local.gates == 2:
            barrier.wait()

    def client():
        assert last_record(output)["event"] == "claimed"
        clients.append(True)
        raise OSError("synthetic stop after exclusive claim")

    # Avoid concurrent global dotenv manipulation in this synchronous runner:
    # race the actual gate/claim, with frozen preparation supplied to each racer.
    monkeypatch.setattr(r, "prepare", lambda: prepared)
    monkeypatch.setattr(r, "live_gate", synchronized_gate)
    monkeypatch.setattr(r, "_read_key", lambda: (reads.append(True), secret())[-1])
    monkeypatch.setattr(r, "make_client", client)

    def invoke():
        try:
            r.run_live(prepared, *args)
        except r.Fault as exc:
            return str(exc)
        except OSError:
            return "claimed_client_failure"
        raise AssertionError("synthetic client should stop")

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: invoke(), range(2)))
    assert sorted(results) == ["claimed_client_failure", "occupied_output"]
    assert len(reads) == 2 and clients == [True] and output.is_dir()


@pytest.mark.parametrize("kind", ("raw-key", "malformed", "json-echo", "escaped", "nested", "depth", "escape-depth"))
def test_unsafe_response_never_persists_body_or_digest(prepared, tmp_path, capsys, kind):
    """The v1 pre-screen hash could persist SHA256(raw credential) on failure."""
    token = "fake.complete/~+token=="
    payload = envelope()
    encoded = "".join(f"\\u{ord(char):04x}" for char in token)
    if kind == "json-echo":
        payload["secret"] = token
    if kind == "escaped":
        payload["secret"] = encoded
    if kind == "nested":
        payload["choices"][0]["message"]["content"] = json.dumps({encoded: {"nested": encoded}})
    if kind == "depth":
        nested = "innocent"
        for _ in range(34):
            nested = [nested]
        payload["extra"] = nested
    if kind == "escape-depth":
        # Each decode exposes one further unicode escape, without huge strings.
        payload["extra"] = "\\" + "u005c" * 20 + "u0061"
    body = r.wire(payload)
    if kind == "raw-key":
        body = token.encode()
    if kind == "malformed":
        body = b'{"secret":"' + encoded.encode()
    client = FakeClient(tmp_path, FakeResponse(body), key=token)
    with pytest.raises(r.Fault):
        r._execute(prepared, tmp_path, client, secret(token))
    record = last_record(tmp_path)
    assert record["response_sha256"] is None
    assert record["usage"]["status"] == ("unknown" if kind in ("raw-key", "malformed") else "known")
    if record["usage"]["status"] == "known":
        assert record["usage"]["input_tokens"] == 900 and record["usage"]["output_tokens"] == 40
    assert len(client.calls) == 1
    assert not list(tmp_path.glob("*.response.json"))
    assert not list(tmp_path.glob("*.model.txt"))
    assert not list(tmp_path.glob("*.delivery.json"))
    all_bytes = b"".join(path.read_bytes() for path in tmp_path.iterdir())
    public = capsys.readouterr()
    all_bytes += (public.out + public.err).encode()
    for forbidden in (token, encoded, r.sha(body), r.sha(token.encode())):
        assert forbidden.encode() not in all_bytes


def test_extraction_changes_neither_dotenv_nor_host_framework_state():
    """The old dotenv-only attempt is replaced, not relabelled as private."""
    import dotenv.main

    original = dotenv.main.DotEnv._get_stream
    environment = dict(os.environ)
    framework = {name: value for name, value in sys.modules.items()
                 if name.startswith(("crewai", "academic_agent.evidence"))}
    first = r.production()
    assert r.production() is first
    assert dotenv.main.DotEnv._get_stream is original and dict(os.environ) == environment
    assert framework == {name: value for name, value in sys.modules.items()
                         if name.startswith(("crewai", "academic_agent.evidence"))}


def test_v1_fixture_requests_and_arm_roots_are_unchanged(prepared):
    """This is execution-boundary succession, never a retuned comparison cohort."""
    assert prepared["manifest"]["fixture_sha256"] == "4ee81119c3e680e96c8904ac0946e6d96a91a06fd5a84fd101966809301fef4a"
    assert prepared["manifest"]["request_sha256"] == [
        "69053fc69d5730144c72a59527e16b8fcb8321fc91ff0636c29499ed2e480e0a",
        "12986a41ab0f4f4e79f7236621c4220bf45886a86b9254a3e13299ec4c365742",
        "fc2ff9a1ec88b066261ab8cca581f391621b89b40fd2ea88da3cf3cddc01a9f0",
        "fda1321d891c0f2c15edfaf968443d9f9aa6f9b834610608a85900e16e8e2ced",
        "3778c7035ef92c16d2b36f2914f43c3ee946897af121c175353cda2a1d4a3e37",
        "f68853ef0cd3fb5e54178780c71fbaf85ce3f885ecf09d4a940fe23f26ee2a5c",
    ]
    assert r.REVISIONS == {"before": "ee0a00e442735cb78c6950eb55d0e4fe1398a9bf",
                           "after": "ff5dcee18f91672ea368e2bdb110f02377df80d5"}
    assert prepared["manifest"]["contract"]["output"] == "outputs/reviewer_comparison_v2_native"


def test_exact_extraction_retains_real_models_and_compiled_bodies(prepared):
    """Real schemas/body implementations survive extraction, without fake module identity."""
    from pydantic import BaseModel, ValidationError

    exports = r.production()
    namespace, _bindings, derived_code, _exports = s._CACHE["evidence"]
    descriptor = prepared["manifest"]["source_loader"]["sources"]["evidence"]
    assert (descriptor["original_top_nodes"], descriptor["retained_top_nodes"]) == (97, 92)
    assert [tuple(item["node"]) for item in descriptor["omissions"]] == list(s.OMISSIONS)
    assert not s.OMITTED_NAMES.intersection(namespace)
    assert "__spec__" not in namespace and "__file__" not in namespace
    assert namespace["__name__"] not in sys.modules
    assert all(issubclass(exports[name], BaseModel) for name in (
        "EvidenceSource", "EvidenceFinding", "EvidenceReport", "ReviewerCorrection", "ReviewerCorrectionPlan"))
    with pytest.raises(ValidationError):
        exports["ReviewerCorrectionPlan"].model_validate({"corrections": [], "unrequested": True})
    full = compile((r.ROOT / "src/academic_agent/evidence.py").read_bytes(), "<comparison-only>",
                   "exec", dont_inherit=True, optimize=0)
    full_codes = s._code_index(full)
    derived_codes = s._code_index(derived_code)
    assert len([c for c in derived_code.co_consts if isinstance(c, CodeType)]) == 41
    for name, code in derived_codes.items():
        assert code == full_codes[name], name  # Code equality excludes the honest filename label.
        assert code.co_filename == derived_code.co_filename
    assert prepared["facts"]["helper_runtime"] == s.runtime_identity()
    context = r.production("run_spec")["DecisionContext"]
    assert context.__pydantic_complete__ and context().crew_inputs()["assessment_mode"] == "orientation"
    for model in r.reports_for(prepared["cases"][0]):
        assert model.__class__ is exports["EvidenceReport"]
        assert model.__class__.__module__.startswith("reviewer_comparison_v2.source_locked_evidence_")


@pytest.mark.parametrize("fault", ("source", "alias", "position", "reference", "import", "dynamic", "omission-set"))
def test_extraction_refuses_unexpected_source_ast_or_import_before_execution(monkeypatch, fault):
    """No TaskOutput stand-in, extra deletion or new import can repair a changed source."""
    raw = (r.ROOT / "src/academic_agent/evidence.py").read_bytes()
    if fault == "source":
        raw += b"\n"
    elif fault == "alias":
        raw = raw.replace(b"from crewai import TaskOutput", b"from crewai import TaskOutput as Other")
    elif fault == "position":
        raw = raw.replace(b"def make_scoring_guardrail(", b"\ndef make_scoring_guardrail(")
    elif fault == "reference":
        raw = raw.replace(b"import socket", b"socket = TaskOutput")
    elif fault == "import":
        raw = raw.replace(b"import socket", b"import crewai_core")
    elif fault == "dynamic":
        raw = raw.replace(b"import socket", b'socket = __import__("socket")')
    elif fault == "omission-set":
        monkeypatch.setattr(s, "OMISSIONS", s.OMISSIONS[:-1])
    if fault not in ("source", "omission-set"):
        # Deliberately get beyond the byte lock to exercise the structural gate;
        # no production bytes, public manifest or live allowance is changed.
        monkeypatch.setitem(s.SOURCE_LOCKS, "evidence", r.sha(raw.replace(b"\r\n", b"\n")))
    with pytest.raises(s.SourceFault):
        s._derive("evidence", raw)


@pytest.mark.parametrize("fault", ("node", "order", "filename", "code", "model-method"))
def test_derived_tree_and_runtime_code_tampering_refuse(monkeypatch, fault):
    """A real function's filename/body and every retained AST node are identity inputs."""
    exports = r.production()
    if fault in ("filename", "code", "model-method"):
        function = (exports["EvidenceSource"].serialize_url if fault == "model-method"
                    else exports["validate_final_report"])
        code = function.__code__
        if fault == "code":
            code = (lambda *_args: []).__code__
        else:
            code = code.replace(co_filename="<foreign-derived-code>")
        monkeypatch.setattr(function, "__code__", code)
        with pytest.raises(s.SourceFault, match="derived_code_drift"):
            s.load()
    else:
        original = s._derive

        def changed(name, raw):
            tree, descriptor = original(name, raw)
            if name == "evidence":
                if fault == "node":
                    tree.body[-1] = ast.Pass(lineno=1, col_offset=0)
                else:
                    tree.body.reverse()
                descriptor["derived_ast_sha256"] = s._ast_sha(tree)
            return tree, descriptor

        monkeypatch.setattr(s, "_derive", changed)
        with pytest.raises(s.SourceFault, match="derived_manifest_drift"):
            s.load()


@pytest.mark.parametrize("fault", ("entrypoint", "cached-plugin", "loading", "cache-shape", "cache-function", "version"))
def test_plugin_and_package_admission_precedes_even_cached_helpers(monkeypatch, fault):
    """An ambient installed/cached plugin never becomes an implicitly trusted validator."""
    r.production()
    import pydantic.plugin._loader as plugin_loader

    if fault == "entrypoint":
        monkeypatch.setattr(s.importlib.metadata, "entry_points", lambda **_kwargs: (object(),))
    elif fault == "cached-plugin":
        monkeypatch.setattr(plugin_loader, "_plugins", {"untrusted": object()})
    elif fault == "loading":
        monkeypatch.setattr(plugin_loader, "_loading_plugins", True)
    elif fault == "cache-shape":
        monkeypatch.setattr(plugin_loader, "_plugins", [])
    elif fault == "cache-function":
        monkeypatch.setattr(plugin_loader, "get_plugins", lambda: ())
    else:
        monkeypatch.setattr(s.importlib.metadata, "version", lambda _name: "unrecognized")
    for name in ("evidence", "run_spec"):
        with pytest.raises(s.SourceFault, match="plugin|dependency"):
            s.load(name)


def test_cold_plugin_gate_precedes_derived_execution(monkeypatch):
    """Installed plugin refusal happens before any model metaclass or constructor."""
    monkeypatch.setattr(s, "_CACHE", {})
    monkeypatch.setattr(s.importlib.metadata, "entry_points", lambda **_kwargs: (object(),))
    monkeypatch.setattr(s, "exec", lambda *_args: pytest.fail("plugin reached execution"), raising=False)
    with pytest.raises(s.SourceFault, match="pydantic_plugins_not_empty"):
        s.load()


def test_runtime_code_digest_is_independent_of_diagnostic_object_references():
    """marshal(code) changed identity when the fidelity check held nested code refs."""
    raw = (r.ROOT / "src/academic_agent/evidence.py").read_bytes()
    tree, _descriptor = s._derive("evidence", raw)
    code = compile(tree, "<identity-regression>", "exec", dont_inherit=True, optimize=0)
    before = s._code_sha(code)
    held = s._code_index(code)
    assert len(held) == 63 and s._code_sha(code) == before
    assert s._code_sha(code.replace(co_filename="<other-label>")) != before
    assert s._code_sha(code.replace(co_consts=(*code.co_consts, "additional-constant"))) != before


@pytest.mark.parametrize("kind", (
    "raw-number", "raw-lexeme", "nested-number", "canonical-float",
    "usage-prompt", "usage-completion", "derived-usage-cost", "malformed-number",
))
def test_numeric_secret_response_and_usage_never_reach_persistence(prepared, tmp_path, monkeypatch, capsys, kind):
    """JSON numbers and derived ledger values can equal an admitted Bearer secret."""
    token = "1234567890"
    payload = envelope()
    if kind == "raw-lexeme":
        # The exact raw credential disappears on JSON float serialization:
        # this specifically requires the raw screen, not the numeric screen.
        token = "1234567890e0"
    elif kind == "nested-number":
        payload["extra"] = [{"count": int(token)}]
    elif kind == "canonical-float":
        payload["extra"] = 0
    elif kind == "usage-prompt":
        payload["usage"] = {"prompt_tokens": int(token), "completion_tokens": 40,
                            "total_tokens": int(token) + 40}
    elif kind == "usage-completion":
        payload["usage"] = {"prompt_tokens": 900, "completion_tokens": int(token),
                            "total_tokens": int(token) + 900}
    elif kind == "derived-usage-cost":
        # Not present in the HTTP response; appears only after accounting math.
        token = "0.000653873"
        payload["usage"] = {"prompt_tokens": 901, "completion_tokens": 40, "total_tokens": 941}
        assert r.observed_usage(payload)["usd_estimate"] == token
    body = r.wire(payload)
    if kind in ("raw-number", "raw-lexeme"):
        body = token.encode()
    elif kind == "canonical-float":
        body = body.replace(b'"extra":0', b'"extra":1.234567890e9')
        assert token.encode() not in body
    elif kind == "derived-usage-cost":
        assert token.encode() not in body
    elif kind == "malformed-number":
        body = token.encode() + b"{"
    client = FakeClient(tmp_path, FakeResponse(body), key=token)
    hashed = []
    original_sha = r.sha

    def observed_sha(data):
        hashed.append(data)
        return original_sha(data)

    monkeypatch.setattr(r, "sha", observed_sha)
    with pytest.raises(r.Fault):
        r._execute(prepared, tmp_path, client, secret(token))
    record = last_record(tmp_path)
    assert record["response_sha256"] is None
    assert body not in hashed, "unsafe response must not even enter response hashing"
    if kind in ("nested-number", "canonical-float"):
        assert record["usage"] == r.observed_usage(envelope())
    else:
        assert record["usage"] == {
            "status": "unknown", "input_tokens": None, "output_tokens": None, "usd_estimate": None,
        }
    assert len(client.calls) == 1
    assert not list(tmp_path.glob("*.response.json"))
    assert not list(tmp_path.glob("*.model.txt"))
    assert not list(tmp_path.glob("*.delivery.json"))
    records = [json.loads(line) for line in (tmp_path / "journal.jsonl").read_text().splitlines()]
    assert [item["event"] for item in records] == ["reserved", "stopped"]
    all_bytes = b"".join(path.read_bytes() for path in tmp_path.iterdir())
    captured = capsys.readouterr()
    all_bytes += (captured.out + captured.err).encode()
    for forbidden in (token, original_sha(body), original_sha(token.encode())):
        assert forbidden.encode() not in all_bytes


@pytest.mark.parametrize("outcome", ("success", "content-echo", "model", "malformed-content", "status"))
def test_numeric_secret_retains_only_independently_safe_usage(prepared, tmp_path, outcome):
    """Safe numeric accounting survives a separate content failure or credential echo."""
    token = "1234567890"
    payload = envelope()
    if outcome == "content-echo":
        payload["choices"][0]["message"]["content"] = token
    elif outcome == "model":
        payload["model"] = "unrequested-model"
    elif outcome == "malformed-content":
        payload["choices"][0]["message"]["content"] = "{"
    client = FakeClient(tmp_path, FakeResponse(r.wire(payload), 503 if outcome == "status" else 200), key=token)
    if outcome == "success":
        assert r._execute(prepared, tmp_path, client, secret(token))["mechanically_complete"] == 6
    else:
        with pytest.raises(r.Fault):
            r._execute(prepared, tmp_path, client, secret(token))
    records = [json.loads(line) for line in (tmp_path / "journal.jsonl").read_text().splitlines()]
    usage_records = [item for item in records if item["event"] in ("observed", "stopped")]
    assert usage_records and all(item["usage"] == r.observed_usage(envelope()) for item in usage_records)
    if outcome == "content-echo":
        assert last_record(tmp_path)["response_sha256"] is None
        assert not list(tmp_path.glob("*.response.json"))
    assert len(client.calls) == (6 if outcome == "success" else 1)
    assert token.encode() not in b"".join(path.read_bytes() for path in tmp_path.iterdir())
