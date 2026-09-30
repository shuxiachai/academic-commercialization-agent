"""Offline boundary controls, never native model-quality observations."""

from __future__ import annotations

import builtins
import copy
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace

import pytest

from evals.reviewer_comparison_v1 import runner as r


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
    def __init__(self, output, response=None, error=None):
        self.output = output
        self.response = response or FakeResponse(r.wire(envelope()))
        self.error = error
        self.calls = []

    def stream(self, method, endpoint, **kwargs):
        journal = [json.loads(line) for line in (self.output / "journal.jsonl").read_text().splitlines()]
        assert journal[-1]["event"] == "reserved"
        assert journal[-1]["ordinal"] == len(self.calls) + 1
        assert journal[-1]["request_sha256"] == r.sha(kwargs["content"])
        assert method == "POST" and endpoint == r.ENDPOINT
        assert kwargs["headers"]["Authorization"] == "Bearer test-secret-only"
        self.calls.append(kwargs["content"])
        if self.error:
            raise self.error
        return self.response


def last_record(path):
    return json.loads((path / "journal.jsonl").read_text().splitlines()[-1])


@pytest.mark.parametrize("mode", ("import", "identity"))
def test_default_import_and_cli_do_not_read_credentials_or_connect(mode):
    """Fresh processes catch CrewAI dotenv autoload hidden by pytest imports."""
    script = r'''
import builtins, io, os, pathlib, socket, sys
def denied(*a, **k):
    raise AssertionError("network forbidden")
socket.socket.connect = denied
socket.create_connection = denied
socket.getaddrinfo = denied
for mod in (builtins, io):
    old = mod.open
    def guarded(path, *a, _old=old, **k):
        if isinstance(path, (str, os.PathLike)) and pathlib.Path(path).name == ".env":
            raise AssertionError("credential read")
        return _old(path, *a, **k)
    mod.open = guarded
os.environ.pop("PYTHON_DOTENV_DISABLED", None)
from evals.reviewer_comparison_v1 import runner
assert "academic_agent.evidence" not in sys.modules
assert "crewai" not in sys.modules
import dotenv.main
old_stream = dotenv.main.DotEnv._get_stream
if sys.argv[1] == "identity":
    assert runner.main([]) == 0
assert dotenv.main.DotEnv._get_stream is old_stream
assert "PYTHON_DOTENV_DISABLED" not in os.environ
'''
    result = subprocess.run([sys.executable, "-c", script, mode], cwd=r.ROOT,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    if mode == "identity":
        value = json.loads(result.stdout)
        assert value["mode"] == "identity_only" and value["live_authorized"] is False
        assert "DASHSCOPE_API_KEY" not in result.stdout


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
        real = r.production()
        wrong = SimpleNamespace(**vars(real))
        wrong.__file__ = str(r.ROOT.parent / "foreign" / "evidence.py")
        original = r.importlib.import_module
        monkeypatch.setattr(r.importlib, "import_module", lambda name: wrong if name == "academic_agent.evidence" else original(name))
        with pytest.raises(r.Fault, match="helper_origin_mismatch"):
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
        r._execute(prepared, tmp_path, client, "test-secret-only")
    assert len(client.calls) == (1 if point == "response" else 0)
    if point == "response":
        assert last_record(tmp_path)["usage"]["status"] == "known"


def test_six_sequential_calls_keep_reservations_and_blind_final_text(prepared, monkeypatch, tmp_path):
    """Mechanically valid bad no-op answers still finish all six, without gain."""
    syncs = []
    original = r.os.fsync
    monkeypatch.setattr(r.os, "fsync", lambda fd: (syncs.append(fd), original(fd))[-1])
    client = FakeClient(tmp_path)
    result = r._execute(prepared, tmp_path, client, "test-secret-only")
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
        r._execute(prepared, tmp_path, client, "test-secret-only")
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
        r._execute(prepared, tmp_path, client, "test-secret-only")
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
        r._execute(prepared, tmp_path, client, "test-secret-only")
    assert len(client.calls) == 1


@pytest.mark.parametrize("usage", (None, {}, {"prompt_tokens": True, "completion_tokens": 2, "total_tokens": 3},
                                  {"prompt_tokens": 100, "completion_tokens": 2, "total_tokens": 4},
                                  {"prompt_tokens": 16385, "completion_tokens": 2, "total_tokens": 16387},
                                  {"prompt_tokens": 100, "completion_tokens": 1501, "total_tokens": 1601}))
def test_unknown_usage_is_not_zero_and_overflow_stops(prepared, tmp_path, usage):
    """Missing/inconsistent counts cannot refund reservations or become free."""
    client = FakeClient(tmp_path, FakeResponse(r.wire(envelope(usage=usage))))
    with pytest.raises(r.Fault, match="unknown_usage|usage_overflow"):
        r._execute(prepared, tmp_path, client, "test-secret-only")
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
        r._execute(prepared, tmp_path, client, "test-secret-only")
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
        assert r.parse_key(key_text) == "sk-synthetic-key123"
    else:
        with pytest.raises(r.Fault):
            r.parse_key(key_text)
