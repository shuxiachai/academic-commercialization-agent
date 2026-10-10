"""Explicit zero-provider checks; excluded from default test_*.py collection.

Synthetic keys only. Process tests launch real Python children; wire tests
intercept the actual stdlib HTTPSConnection.send method before any socket opens.
"""

from __future__ import annotations

import ast
import base64
import http.client
import json
import shutil
import subprocess
import sys
import threading
import time
from decimal import Decimal

import pytest

from evals.reviewer_reason_schema_probe_v1 import core, runner, worker

KEY = "sk-synthetic-key-never-valid-123456789"


def response(reason="OK.", *, content=None, model=core.MODEL, usage=True):
    result = {"model": model, "choices": [{"index": 0, "finish_reason": "stop",
              "message": {"role": "assistant", "content": json.dumps({"reason": reason}) if content is None else content}}]}
    if usage:
        result["usage"] = {"prompt_tokens": 500, "completion_tokens": 25, "total_tokens": 525}
    return result


def observe(value, case="RSP01", status=200):
    return core.observe(status, core.canonical(value), case, KEY)


@pytest.fixture
def private(tmp_path, monkeypatch):
    root = tmp_path / "isolated"
    for name in core.SOURCE_FILES:
        destination = root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(core.ROOT / name, destination)
    (root / ".git").mkdir()
    (root / ".git" / "HEAD").write_text("a" * 40 + "\n", encoding="ascii")
    (root / "outputs").mkdir()
    key_path = root / "outputs" / "fake.env"
    packet_path = root / "outputs" / "synthetic-packet.json"
    value = {"schema": "reviewer-reason-schema-private-packet-v1",
             "endpoint": "https://synthetic-workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions",
             "model": core.MODEL, "credential_path": str(key_path), "credential_variable": "DASHSCOPE_API_KEY",
             "rates": {"currency": "CNY", "input_per_million": "2", "output_per_million": "8",
                       "input_tier_max": 256000, "discounts": "none", "input_estimate": 12288,
                       "output_ceiling": 1500, "reservation": "0.04", "batch_soft_stop": "0.12"}}
    packet_path.write_bytes(core.canonical(value))
    identity = core.identity(packet_path, root)
    grant_path = root / "outputs" / "synthetic-grant.json"
    grant = {"schema": "reviewer-reason-schema-execution-grant-v1", "identity": identity["identity"],
             "commit": identity["commit"], "review_source_identity": identity["source_identity"],
             "review_verdict": "approved", "review_artifact_sha256": "b" * 64,
             "ci_source_identity": identity["source_identity"], "ci_commit": identity["commit"],
             "ci_conclusion": "success", "ci_run": "synthetic-offline-control",
             "explicit_authorization": "one new synthetic batch; bound endpoint and selected credential read",
             "max_requests": 3, "soft_stop_cny": "0.12"}
    grant_path.write_bytes(core.canonical(grant))
    monkeypatch.setattr(runner, "require_committed", lambda _root: None)
    return root, packet_path, grant_path, identity, key_path


def dispatch(private):
    root, packet_path, grant_path, identity, _key_path = private
    return runner.dispatch(packet_path, grant_path, identity["identity"], identity["commit"], root)


def scripted_child(monkeypatch, answer):
    calls = []

    def child(command, deadline, cwd):
        case = command[-1]
        calls.append(case)
        output = cwd / "outputs" / core.NATIVE_OUTPUT
        reservation = core.strict_json((output / (case + ".reservation.json")).read_bytes())
        assert reservation["reserved_cny"] == "0.04"
        assert reservation["body_sha256"] == core.digest((output / (case + ".request.json")).read_bytes())
        assert deadline > time.monotonic()
        result = answer(case)
        return {"state": "completed", "physical_exit": True, "pipes_drained": True}, core.canonical(result)

    monkeypatch.setattr(runner, "run_child", child)
    return calls


def test_default_identity_reads_no_key_and_creates_no_execution_output(private, monkeypatch, capsys):
    """The default command previously risked turning preparation into execution."""
    root, packet_path, _grant, _identity, key_path = private
    real_identity = core.identity
    monkeypatch.setattr(core, "identity", lambda path: real_identity(path, root))

    def forbidden(*_args, **_kwargs):
        raise AssertionError("identity-only attempted execution/key access")

    monkeypatch.setattr(core, "read_selected_key", forbidden)
    monkeypatch.setattr(runner, "run_child", forbidden)
    monkeypatch.setattr(worker, "one_post", forbidden)
    before = sorted(str(path.relative_to(root)) for path in root.rglob("*"))
    assert runner.main(["--packet", str(packet_path)]) == 0
    captured = capsys.readouterr().out
    value = json.loads(captured)
    assert value["mode"] == "identity_only" and value["credential_reads"] == 0
    assert "synthetic-workspace" not in captured and str(key_path) not in captured
    assert not key_path.exists()
    assert before == sorted(str(path.relative_to(root)) for path in root.rglob("*"))


def test_frozen_body_schema_unicode_and_parameters():
    """The 300-code-point control must survive request construction unchanged."""
    for case in core.CASES:
        body = core.request_body(case)
        value = core.strict_json(body)
        assert len(body) <= 8192
        assert value["model"] == "qwen3.7-plus-2026-05-26"
        assert value["temperature"] == 0 and value["max_tokens"] == 1500
        assert value["enable_thinking"] is False and value["stream"] is False
        assert value["response_format"] == {"type": "json_schema", "json_schema": {
            "name": "reviewer_reason_probe_v1", "strict": True, "schema": {
                "type": "object", "properties": {"reason": {"type": "string", "minLength": 3, "maxLength": 300}},
                "required": ["reason"], "additionalProperties": False}}}
        assert value["messages"][1]["content"] == "Copy this literal exactly into reason: " + core.literal(case)
    unicode_literal = core.literal("RSP02")
    assert len(unicode_literal) == 300
    assert len(unicode_literal.encode("utf-8")) == 1051
    assert len(unicode_literal.encode("utf-16-le")) // 2 == 451
    estimate = (Decimal(12288) * 2 + Decimal(1500) * 8) / 1000000
    assert estimate == Decimal("0.036576") < Decimal(core.RESERVATION_CNY)
    assert Decimal(core.RESERVATION_CNY) * 3 == Decimal(core.BATCH_SOFT_CNY)


@pytest.mark.parametrize("case,reason,disposition", [
    ("RSP01", "OK.", "conforming_literal"), ("RSP02", "界" * 149 + "😀" * 151, "conforming_literal"),
    ("RSP03", "A" * 3, "conforming_under_pressure"), ("RSP03", "A" * 300, "conforming_under_pressure"),
    ("RSP03", "A" * 301, "local_contract_failed"), ("RSP03", "A" * 2, "local_contract_failed"),
    ("RSP03", "Explanation", "control_mismatch"), ("RSP01", " OK.", "control_mismatch"),
    ("RSP02", "界" * 148 + "😀" * 152, "control_mismatch"),
])
def test_exact_boundaries_without_repair(case, reason, disposition):
    """Clipping, stripping and Unicode normalization would erase the defect."""
    raw = core.canonical(response(reason))
    result = core.observe(200, raw, case, KEY)
    assert result["disposition"] == disposition
    assert base64.b64decode(result["response_base64"]) == raw
    assert result["response_sha256"] == core.digest(raw)


@pytest.mark.parametrize("content", [
    '{"reason":"OK.","reason":"BAD"}', '{"reason":NaN}', '{"reason":true}',
    '{"reason":123}', '{"reason":null}', '{"reason":[]}', '{"reason":{}}',
    '{"reason":"OK.","extra":1}', '{}', '[]', '```json\n{"reason":"OK."}\n```',
    '{"reason":"\\ud800"}', '{"reason":"OK."} trailing',
])
def test_strict_inner_json(content):
    """Bad JSON or an extra field cannot be repaired into a passing response."""
    result = observe(response(content=content))
    assert result["schema"] == "failed" and not result["continue"]
    assert result["disposition"] == "local_contract_failed"


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}',
                                  b'{"x":"\xff"}', b'{"x":"\\udfff"}', b'{"x":1e999}'])
def test_strict_entire_envelope(raw):
    """Envelope-level duplicates, nonfinite numbers and lone surrogates are invalid."""
    with pytest.raises(core.ProbeError):
        core.strict_json(raw)


@pytest.mark.parametrize("mutation,expected", [
    (lambda value: value.update(model="qwen3.7-plus"), "envelope_or_model"),
    (lambda value: value.pop("model"), "envelope_or_model"),
    (lambda value: value["choices"][0].update(finish_reason="length"), "finish_or_content"),
    (lambda value: value["choices"][0].update(index=False), "finish_or_content"),
    (lambda value: value["choices"][0]["message"].update(reasoning_content="thinking"), "finish_or_content"),
    (lambda value: value["choices"][0]["message"].update(tool_calls=[{}]), "finish_or_content"),
])
def test_envelope_gates_preserve_known_usage(mutation, expected):
    """A snapshot alias or incomplete delivery must not become schema evidence."""
    value = response()
    mutation(value)
    result = observe(value)
    assert result["failure"] == expected and result["usage"]["state"] == "known"
    assert not result["continue"] and result["schema"] == "not_checked"


def test_refusal_is_explicit_and_not_a_prose_guess():
    """Only the machine-readable refusal field establishes refusal."""
    value = response()
    value["choices"][0]["message"]["refusal"] = "declined"
    assert observe(value)["disposition"] == "provider_refusal"
    assert observe(response("I cannot comply"))["disposition"] == "control_mismatch"


@pytest.mark.parametrize("usage", [None, {}, {"prompt_tokens": True, "completion_tokens": 1, "total_tokens": 2},
    {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 3},
    {"prompt_tokens": -1, "completion_tokens": 1, "total_tokens": 0},
    {"prompt_tokens": 12289, "completion_tokens": 1, "total_tokens": 12290},
    {"prompt_tokens": 10, "completion_tokens": 1501, "total_tokens": 1511},
    {"prompt_tokens": 256001, "completion_tokens": 1, "total_tokens": 256002},
    {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "completion_tokens_details": {"reasoning_tokens": 1}},
])
def test_unknown_overestimate_or_wrong_tier_stops(usage):
    """Known schema/control success cannot refund unknown accounting."""
    value = response()
    value["usage"] = usage
    result = observe(value)
    assert result["schema"] == "passed" and result["control"] == "passed"
    assert result["usage"]["state"] != "known" and not result["continue"]


@pytest.mark.parametrize("status,expected", [(400, "api_rejected"), (401, "access_unavailable"),
    (403, "access_unavailable"), (429, "access_unavailable"), (302, "observation_unavailable"),
    (500, "observation_unavailable")])
def test_api_disposition_separate_from_schema(status, expected):
    result = observe({"error": {"message": "synthetic"}}, status=status)
    assert result["disposition"] == expected and result["schema"] == "not_checked"
    assert result["usage"]["state"] == "unknown" and not result["continue"]


@pytest.mark.parametrize("layers", [0, 1, 2, 5])
def test_key_echo_withholds_content_and_digest_but_retains_safe_usage(layers):
    """JSON escaping must not smuggle an echoed key into the private journal."""
    escaped = KEY if layers == 0 else "".join(f"\\u{ord(char):04x}" for char in KEY)
    for _ in range(max(0, layers - 1)):
        escaped = json.dumps(escaped)
    value = response(escaped)
    raw = core.canonical(value)
    result = core.observe(200, raw, "RSP01", KEY)
    assert result["failure"] == "credential_echo_withheld"
    assert "response_base64" not in result and "response_sha256" not in result
    assert core.digest(raw) not in core.canonical(result).decode()
    assert result["usage"]["state"] == "known" and not result["continue"]


def test_real_http_send_boundary_has_exact_frozen_body_and_no_proxy(monkeypatch):
    """Inspect bytes handed to stdlib send, not a high-level request field."""
    sent = []
    monkeypatch.setenv("HTTPS_PROXY", "http://must-not-be-used.invalid:9")
    monkeypatch.setattr(http.client.HTTPSConnection, "send", lambda _self, data: sent.append(data))

    class Reply:
        status = 200

        def read(self, amount):
            assert amount == core.RESPONSE_LIMIT + 1
            return core.canonical(response())

        def getheader(self, name, default=None):
            return default

    monkeypatch.setattr(http.client.HTTPSConnection, "getresponse", lambda _self: Reply())
    body = core.request_body("RSP01")
    result = worker.one_post("https://synthetic.invalid/compatible-mode/v1/chat/completions", body, body, KEY, "RSP01")
    assert result["continue"]
    assert len(sent) == 2 and sent[1] == body
    assert b"POST /compatible-mode/v1/chat/completions HTTP/1.1" in sent[0]
    assert b"Host: synthetic.invalid" in sent[0]
    assert ("Content-Length: " + str(len(body))).encode() in sent[0]
    wire = core.strict_json(sent[1])
    assert wire["response_format"]["json_schema"]["schema"]["properties"]["reason"]["maxLength"] == 300
    changed = dict(wire)
    changed.pop("response_format")
    sent.clear()
    with pytest.raises(core.ProbeError, match="wire_bytes_changed"):
        worker.one_post("https://synthetic.invalid/path", core.canonical(changed), body, KEY, "RSP01")
    assert sent == []
    with pytest.raises(core.ProbeError):
        worker.send_frozen(object(), core.canonical(changed), body)


def test_response_bound_probes_extra_byte_and_closes_connection(monkeypatch):
    class Reply:
        status = 200

        def read(self, amount):
            assert amount == core.RESPONSE_LIMIT + 1
            return b" " * amount

        def getheader(self, _name, default=None):
            return default

    monkeypatch.setattr(http.client.HTTPSConnection, "send", lambda *_args: None)
    monkeypatch.setattr(http.client.HTTPSConnection, "getresponse", lambda _self: Reply())
    body = core.request_body("RSP01")
    result = worker.one_post("https://synthetic.invalid/path", body, body, KEY, "RSP01")
    assert result["failure"] == "response_too_large" and not result["continue"]
    assert "response_base64" not in result and "response_sha256" not in result


@pytest.mark.parametrize("fault", ["schema", "model", "refusal", "usage", "control"])
def test_first_fault_leaves_two_not_run_and_never_redispatches(private, monkeypatch, fault):
    """A correct first reservation must not authorize another request after failure."""
    def answer(case):
        value = response("A" * 301 if fault == "schema" else "OK.")
        if fault == "model":
            value["model"] = "wrong"
        if fault == "refusal":
            value["choices"][0]["message"]["refusal"] = "declined"
        if fault == "usage":
            value.pop("usage")
        if fault == "control":
            value["choices"][0]["message"]["content"] = '{"reason":"BAD"}'
        return observe(value, case)

    calls = scripted_child(monkeypatch, answer)
    result = dispatch(private)
    assert calls == ["RSP01"]
    assert [row["disposition"] for row in result["cases"][1:]] == ["not_run", "not_run"]
    assert result["status"] == "unavailable" and result["reserved_cny"] == "0.04"
    with pytest.raises(FileExistsError):
        dispatch(private)
    assert calls == ["RSP01"]


def test_all_three_slots_and_separate_observations(private, monkeypatch):
    calls = scripted_child(monkeypatch, lambda case: observe(response(
        "A" * 300 if case == "RSP03" else core.literal(case)), case))
    result = dispatch(private)
    assert calls == list(core.CASES)
    assert result["status"] == "observed_small_contract_compatibility"
    assert result["reserved_cny"] == "0.12"
    assert all(row["schema"] == row["control"] == "passed" for row in result["cases"])


@pytest.mark.parametrize("suffix,expected_calls", [("reservation.json", 0), ("observation.json", 1)])
def test_persistence_failure_seals_output_and_stops(private, monkeypatch, suffix, expected_calls):
    calls = scripted_child(monkeypatch, lambda case: observe(response(), case))
    original = core.durable_new

    def fail(path, raw):
        if path.name == "RSP01." + suffix:
            raise OSError("synthetic disk failure")
        original(path, raw)

    monkeypatch.setattr(core, "durable_new", fail)
    result = dispatch(private)
    assert len(calls) == expected_calls
    assert result["cases"][0]["failure"] == "preflight_or_evidence_persistence_failed"
    assert [row["disposition"] for row in result["cases"][1:]] == ["not_run", "not_run"]
    with pytest.raises(FileExistsError):
        dispatch(private)


def test_worker_claim_precedes_key_and_is_not_reusable(private, monkeypatch):
    """Even a second worker for the same reservation cannot repeat the POST."""
    root, packet_path, grant_path, identity, key_path = private
    output = root / "outputs" / core.NATIVE_OUTPUT
    output.mkdir()
    body = core.request_body("RSP01", root)
    core.durable_new(output / "RSP01.request.json", body)
    reservation = {"schema": "reviewer-reason-schema-reservation-v1", "case": "RSP01",
                   "identity": identity["identity"], "grant_sha256": core.digest(grant_path.read_bytes()),
                   "body_sha256": core.digest(body), "reserved_cny": "0.04"}
    core.durable_new(output / "RSP01.reservation.json", core.canonical(reservation))
    key_path.write_text("DASHSCOPE_API_KEY='" + KEY + "'\nOTHER_KEY=not_selected\n", encoding="utf-8")
    real_read = core.read_selected_key
    calls = []

    def read(config):
        assert (output / "RSP01.dispatch-claimed.json").exists()
        calls.append("key")
        return real_read(config)

    def post(_endpoint, actual, frozen, key, case):
        assert actual == frozen == body and key == KEY
        calls.append("post")
        return observe(response(), case)

    monkeypatch.setattr(core, "read_selected_key", read)
    monkeypatch.setattr(worker, "one_post", post)
    assert worker.execute(packet_path, grant_path, identity["identity"], "RSP01", root)["continue"]
    with pytest.raises(FileExistsError):
        worker.execute(packet_path, grant_path, identity["identity"], "RSP01", root)
    assert calls == ["key", "post"]


@pytest.mark.parametrize("target", ["packet", "body", "source", "grant"])
def test_changed_bindings_stop_before_child(private, monkeypatch, target):
    root, packet_path, grant_path, _identity, _key_path = private
    if target == "packet":
        packet_path.write_bytes(packet_path.read_bytes() + b"\n")
    elif target == "body":
        path = root / core.SOURCE_FILES[4]
        path.write_bytes(path.read_bytes().replace(b"mandatory", b"optional"))
    elif target == "source":
        path = root / core.SOURCE_FILES[0]
        path.write_bytes(path.read_bytes() + b"\n")
    else:
        value = json.loads(grant_path.read_bytes())
        value["ci_conclusion"] = "pending"
        grant_path.write_bytes(core.canonical(value))
    calls = scripted_child(monkeypatch, lambda case: observe(response(), case))
    with pytest.raises(core.ProbeError):
        dispatch(private)
    assert calls == [] and not (root / "outputs" / core.NATIVE_OUTPUT).exists()


@pytest.mark.parametrize("mode", ["success", "exit", "hang", "stdout", "stderr"])
def test_real_child_exit_deadline_and_full_pipe_bounds(tmp_path, monkeypatch, mode):
    """Real Popen, exit and pipe EOF establish process facts; no fake Popen object."""
    scripts = {"success": "import sys; sys.stdout.buffer.write(b'{}')",
               "exit": "raise SystemExit(9)", "hang": "import time; time.sleep(60)",
               "stdout": "import sys; sys.stdout.buffer.write(b'x' * 300000); sys.stdout.flush()",
               "stderr": "import sys; sys.stderr.buffer.write(b'x' * 20000); sys.stderr.flush()"}
    child = tmp_path / "child.py"
    child.write_text(scripts[mode], encoding="utf-8")
    real_popen = subprocess.Popen
    processes = []

    def record(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", record)
    started = time.monotonic()
    result, raw = runner.run_child([sys.executable, "-I", "-S", "-B", str(child)], started + (0.4 if mode == "hang" else 5), tmp_path)
    assert result["physical_exit"] and result["pipes_drained"]
    assert processes[0].poll() is not None and processes[0].wait(timeout=0) == result["returncode"]
    if mode == "success":
        assert result["state"] == "completed" and raw == b"{}"
    else:
        assert raw == b""
        assert result["state"] == {"exit": "worker_exit_failed", "hang": "deadline_exceeded",
                                    "stdout": "pipe_bound_or_read_fault", "stderr": "pipe_bound_or_read_fault"}[mode]
    assert time.monotonic() - started < 20


def test_real_child_force_kill_and_reap_when_terminate_is_ineffective(tmp_path, monkeypatch):
    """A real sleeping child remains owned until a real kill and wait complete."""
    child = tmp_path / "child.py"
    child.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
    # On Windows TerminateProcess is already forceful. To exercise the fallback
    # on both platforms, suppress only terminate; retain the real Popen/kill/wait.
    monkeypatch.setattr(subprocess.Popen, "terminate", lambda self: None)
    monkeypatch.setattr(runner, "EXIT_SECONDS", 0.1)
    started = time.monotonic()
    result, raw = runner.run_child([sys.executable, "-I", "-S", str(child)], started + 0.3, tmp_path)
    assert result["state"] == "deadline_exceeded" and result["physical_exit"] and result["pipes_drained"]
    assert raw == b"" and time.monotonic() - started < 5


def test_unconfirmed_drain_prevents_next_slot(private, monkeypatch):
    """Fault-injected unconfirmed ownership is never treated as actual exit evidence."""
    calls = []

    def unknown(command, _deadline, _cwd):
        calls.append(command[-1])
        return {"state": "drain_unconfirmed", "physical_exit": False, "pipes_drained": False}, b""

    monkeypatch.setattr(runner, "run_child", unknown)
    result = dispatch(private)
    assert calls == ["RSP01"]
    assert result["cases"][0]["process"]["physical_exit"] is False
    assert [row["disposition"] for row in result["cases"][1:]] == ["not_run", "not_run"]


def test_worker_import_surface_and_clean_child_environment(monkeypatch):
    """No SDK/production import, proxy inheritance, worker thread or child launcher."""
    for name in ("OPENAI_API_KEY", "DASHSCOPE_API_KEY", "HTTPS_PROXY", "PYTHONPATH"):
        monkeypatch.setenv(name, KEY)
    assert all(name not in runner.clean_environment() for name in
               ("OPENAI_API_KEY", "DASHSCOPE_API_KEY", "HTTPS_PROXY", "PYTHONPATH"))
    tree = ast.parse((core.ROOT / core.SOURCE_FILES[3]).read_text(encoding="utf-8"))
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imports.update(alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names)
    assert not any(name.startswith(("crewai", "pydantic", "openai", "academic_agent", "threading", "subprocess"))
                   for name in imports)


def test_final_packet_read_is_bound_before_key_or_post(private, monkeypatch):
    """A packet swap after identity/claim must not redirect the endpoint or key source."""
    root, packet_path, grant_path, identity, _key_path = private
    output = root / "outputs" / core.NATIVE_OUTPUT
    output.mkdir()
    body = core.request_body("RSP01", root)
    core.durable_new(output / "RSP01.request.json", body)
    core.durable_new(output / "RSP01.reservation.json", core.canonical({
        "schema": "reviewer-reason-schema-reservation-v1", "case": "RSP01", "identity": identity["identity"],
        "grant_sha256": core.digest(grant_path.read_bytes()), "body_sha256": core.digest(body), "reserved_cny": "0.04"}))
    original_write = core.durable_new
    calls = []

    def swap(path, raw):
        original_write(path, raw)
        if path.name == "RSP01.dispatch-claimed.json":
            changed = core.strict_json(packet_path.read_bytes())
            changed["endpoint"] = "https://different-workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1/chat/completions"
            changed["credential_path"] = str(root / "outputs" / "different-fake.env")
            packet_path.write_bytes(core.canonical(changed))

    def key_read(_config):
        calls.append("key")
        return KEY

    def post(*_args):
        calls.append("post")
        return observe(response())

    monkeypatch.setattr(core, "durable_new", swap)
    monkeypatch.setattr(core, "read_selected_key", key_read)
    monkeypatch.setattr(worker, "one_post", post)
    with pytest.raises(core.ProbeError, match="packet_changed_after_claim"):
        worker.execute(packet_path, grant_path, identity["identity"], "RSP01", root)
    assert calls == []


def test_post_parse_header_exception_stops_after_first_slot(private, monkeypatch):
    """A full passing body followed by a broken HTTP header cannot retain continue=True."""
    monkeypatch.setattr(http.client.HTTPSConnection, "send", lambda *_args: None)

    class Reply:
        status = 200

        def read(self, amount):
            assert amount == core.RESPONSE_LIMIT + 1
            return core.canonical(response())

        def getheader(self, name, default=None):
            return "9" * 5000 if name == "Content-Length" else default

    monkeypatch.setattr(http.client.HTTPSConnection, "getresponse", lambda _self: Reply())

    def answer(case):
        body = core.request_body(case)
        return worker.one_post("https://synthetic.invalid/path", body, body, KEY, case)

    calls = scripted_child(monkeypatch, answer)
    result = dispatch(private)
    first = result["cases"][0]
    assert calls == ["RSP01"] and first["failure"] == "transport_unavailable"
    assert first["continue"] is False and first["disposition"] == "observation_unavailable"
    assert first["usage"]["state"] == "known"
    assert [row["disposition"] for row in result["cases"][1:]] == ["not_run", "not_run"]


def test_overestimate_cost_is_preserved_while_dispatch_stops(private, monkeypatch):
    """Out-of-estimate numeric usage is known expenditure, not zero/unknown cost."""
    value = response()
    value["usage"] = {"prompt_tokens": 12289, "completion_tokens": 25, "total_tokens": 12314}
    calls = scripted_child(monkeypatch, lambda case: observe(value, case))
    result = dispatch(private)
    assert result["cases"][0]["usage"]["state"] == "over_estimate"
    assert Decimal(result["known_estimated_cny"]) == Decimal("0.024778")
    assert calls == ["RSP01"]
    assert [row["disposition"] for row in result["cases"][1:]] == ["not_run", "not_run"]


def test_real_child_reaped_when_second_reader_start_fails(tmp_path, monkeypatch):
    """Reader startup failure after real Popen cannot leak a sleeping worker."""
    child = tmp_path / "child.py"
    child.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
    real_popen = subprocess.Popen
    real_start = threading.Thread.start
    processes = []
    starts = []

    def record(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    def start(thread):
        starts.append(thread)
        if len(starts) == 2:
            raise RuntimeError("synthetic second reader startup fault")
        return real_start(thread)

    monkeypatch.setattr(subprocess, "Popen", record)
    monkeypatch.setattr(threading.Thread, "start", start)
    started = time.monotonic()
    try:
        result, raw = runner.run_child([sys.executable, "-I", "-S", str(child)], started + 5, tmp_path)
        assert processes[0].poll() is not None and processes[0].wait(timeout=0) == result["returncode"]
        assert result["physical_exit"] is True
        assert result["pipes_drained"] is False and result["state"] == "drain_unconfirmed"
        assert raw == b"" and time.monotonic() - started < 5
    finally:
        # Defect re-injection deliberately removes runner cleanup. Test cleanup
        # happens after the ownership assertion and cannot manufacture its pass.
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
