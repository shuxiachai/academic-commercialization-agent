"""Offline CLI/identity and actual policy -> HTTP -> durable batch controls."""

from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
from types import SimpleNamespace
import tomllib

import httpx
from importlib.metadata import PackageNotFoundError
import pytest

import report_evidence_stage_canary as cli
from academic_agent import report_evidence_followup as core
from academic_agent import report_evidence_stage_qwen_canary as canary
from academic_agent.report_evidence_stage_qwen_transport import StageQwenLedger, stage_configuration

KEY = "sk-stage-offline-synthetic-only"
COMMIT = "a" * 40
USAGE = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
REAL_ROOT = canary.ROOT
REAL_GIT = canary._git


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def events(output):
    return [json.loads(line) for line in (output / "events.jsonl").read_text(encoding="utf-8").splitlines()]


def final(ids=(), status="answered", answer="Synthetic result"):
    return {"role": "assistant", "content": json.dumps({
        "answer": answer, "status": status, "evidence_ids": list(ids),
    })}


def native_call(name, arguments, call_id):
    return {"role": "assistant", "content": None, "tool_calls": [{
        "id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)},
    }]}


def native_read(source_id="A7", call_id="native_read", length=1500):
    return native_call("read_source", {"source_id": source_id, "offset": 0, "length": length}, call_id)


def payload(message, **changes):
    return {"model": "qwen3.5-plus", "usage": deepcopy(USAGE), "choices": [{
        "index": 0, "message": message,
        "finish_reason": "tool_calls" if message.get("tool_calls") else "stop",
    }], **changes}


def response(value, status=200, headers=None):
    raw = value if isinstance(value, bytes) else json.dumps(value).encode("utf-8")
    return httpx.Response(status, stream=httpx.ByteStream(raw), headers=headers)


@pytest.fixture(autouse=True)
def offline(tmp_path, monkeypatch):
    """Copy only declared public inputs; no Git, real credentials or real HTTP."""
    repo = tmp_path / "repo"
    committed = {}
    for name in canary.IDENTITY_PATHS:
        destination = repo / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REAL_ROOT / name, destination)
        committed[name] = destination.read_bytes().replace(b"\r\n", b"\n")
    (repo / "outputs").mkdir()
    versions = {row["name"]: row["version"] for row in tomllib.loads(
        (repo / "uv.lock").read_text(encoding="utf-8"))["package"]}
    state = {"repo": repo, "committed": committed, "versions": versions, "git": [], "key_reads": [],
             "requests": [], "handler": None, "http_options": [], "clients": [], "intents": [],
             "output": repo / "outputs" / "batch", "tools": [], "setup_at_dispatch": []}

    def git(*args):
        state["git"].append(args)
        if args[0] == "rev-parse":
            return COMMIT.encode() + b"\n"
        if args[0] == "status":
            return b""
        if args[0] == "show":
            revision, name = args[1].split(":", 1)
            assert revision == COMMIT
            if name not in committed:
                raise subprocess.CalledProcessError(128, ["git", "show"])
            return committed[name]
        pytest.fail("unexpected Git operation")

    class Environment:
        def get(self, name):
            state["key_reads"].append(name)
            assert name == "DASHSCOPE_API_KEY"
            return state.get("key", KEY)

    monkeypatch.setattr(canary, "ROOT", repo)
    monkeypatch.setattr(canary, "_git", git)
    monkeypatch.setattr(canary, "version", versions.__getitem__)
    monkeypatch.setattr(canary, "os", SimpleNamespace(environ=Environment(), path=os.path))
    real_client = httpx.AsyncClient

    def forbidden(*args, **kwargs):
        pytest.fail("non-intercepted HTTP is forbidden")

    async def dispatch(request):
        state["requests"].append(request)
        state["intents"].append(events(state["output"])[-1])
        state["setup_at_dispatch"].append({name: read_json(state["output"] / name)
                                            for name in ("manifest.json", "identity.json", "authorization.json")})
        if state["handler"] is None:
            pytest.fail("unexpected intercepted request")
        return state["handler"](request)

    def transport(**kwargs):
        state["http_options"].append(kwargs)
        return httpx.MockTransport(dispatch)

    def client(**kwargs):
        state["clients"].append(kwargs)
        # Keep Windows Proactor's internal socketpair intact. Only the actual
        # HTTP construction boundary is guarded; this is not a socket sandbox.
        if (not isinstance(kwargs.get("transport"), httpx.MockTransport)
                or kwargs.get("trust_env") is not False or kwargs.get("proxy") is not None or kwargs.get("mounts")):
            forbidden()
        return real_client(**kwargs)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", transport)
    monkeypatch.setattr(httpx, "AsyncClient", client)
    monkeypatch.setattr(httpx, "HTTPTransport", forbidden)
    monkeypatch.setattr(httpx, "Client", forbidden)
    for name in ("lookup_sources", "read_source"):
        original = getattr(core, name)

        def spy(*args, _name=name, _original=original, **kwargs):
            state["tools"].append((_name, deepcopy(kwargs)))
            return _original(*args, **kwargs)

        monkeypatch.setattr(core, name, spy)
    return state


def arguments(offline, paid=False):
    result = ["--expected-commit", COMMIT, "--expected-fixture-sha256", canary.FIXTURE_SHA256]
    if paid:
        result += ["--authorize-paid", canary.PROTOCOL_IDENTITY, "--output-dir", str(offline["output"])]
    return result


def batch(offline):
    return canary.run_canary(expected_commit=COMMIT, expected_fixture_sha256=canary.FIXTURE_SHA256,
                             authorize_paid=canary.PROTOCOL_IDENTITY, output_dir=offline["output"])


def provider(lookup=False):
    """Native calls select the real local tools, never precomputed tool results."""
    def handle(request):
        body = json.loads(request.content)
        negative = "annual sales" in body["messages"][1]["content"]
        source_id = "M4" if negative else "A7"
        prefix = "sq02" if negative else "sq01"
        last = body["messages"][-1]
        if last["role"] != "tool":
            if lookup:
                query = "coastal filter" if negative else "ceramic strain gauge"
                return response(payload(native_call("lookup_sources", {"query": query}, prefix + "_lookup")))
            return response(payload(native_read(source_id, prefix + "_read")))
        result = json.loads(last["content"])
        if "hits" in result:
            return response(payload(native_read(source_id, prefix + "_read")))
        message = (final(status="abstained", answer="The saved text is unavailable; I abstain.") if negative
                   else final([result["evidence_id"]], answer="32 microstrain; no outdoor durability test was performed."))
        return response(payload(message))
    return handle


def assert_no_side_effects(offline):
    assert offline["key_reads"] == []
    assert offline["requests"] == []
    assert list((offline["repo"] / "outputs").iterdir()) == []


def test_default_cli_only_checks_identity(offline, capsys):
    """A successful default CLI invocation must not read a key or create a batch."""
    assert cli.main(arguments(offline)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["mode"] == "identity_only" and result["identity_verified"] is True
    assert result["live_authorized"] is False
    identity = result["identity"]
    assert identity["commit"] == COMMIT and identity["fixture_sha256"] == canary.FIXTURE_SHA256
    assert set(identity["disk_sha256"]) == set(identity["committed_sha256"]) == set(canary.IDENTITY_PATHS)
    assert identity["configuration_sha256"] == hashlib.sha256(canary._encoded(canary.configuration())).hexdigest()
    assert "src/academic_agent/__init__.py" in identity["disk_sha256"]
    assert all(("show", COMMIT + ":" + name) in offline["git"] for name in canary.IDENTITY_PATHS)
    assert_no_side_effects(offline)


@pytest.mark.parametrize("name", ["src/academic_agent/__init__.py", "src/academic_agent/report_evidence_qwen_transport.py",
                                  "src/academic_agent/report_evidence_stage_qwen_canary.py", "pyproject.toml"],
                         ids=["init", "http", "runner", "config"])
def test_hidden_disk_change_fails_before_secret_output_http(offline, capsys, name):
    """Clean status, including assume-unchanged, cannot hide changed executing bytes."""
    with (offline["repo"] / name).open("ab") as stream:
        stream.write(b"\n# hidden from status\n")
    assert cli.main(arguments(offline, paid=True)) == 1
    assert "committed_content_mismatch" in capsys.readouterr().out
    assert_no_side_effects(offline)


@pytest.mark.parametrize("defect", ["head", "dirty", "untracked", "unavailable", "fixture", "ackhash", "shortcommit"])
def test_cli_identity_failures_precede_all_effects(offline, monkeypatch, capsys, defect):
    """Every independent identity failure blocks the actual CLI execution entry."""
    original = canary._git
    args = arguments(offline, paid=True)
    if defect == "ackhash":
        args[3] = "0" * 64
    elif defect == "shortcommit":
        args[1] = "94c27bd"
    elif defect == "fixture":
        path = offline["repo"] / canary.FIXTURE
        changed = path.read_bytes().replace(b"32 microstrain", b"99 microstrain")
        path.write_bytes(changed)
        offline["committed"][canary.FIXTURE] = changed
    elif defect == "untracked":
        del offline["committed"]["report_evidence_stage_canary.py"]
    else:
        def git(*operation):
            if defect == "unavailable":
                raise subprocess.TimeoutExpired("git", 10)
            if defect == "head" and operation[0] == "rev-parse":
                return b"b" * 40
            if defect == "dirty" and operation[0] == "status":
                return b" M report_evidence_stage_canary.py\n"
            return original(*operation)
        monkeypatch.setattr(canary, "_git", git)
    assert cli.main(args) == 1
    assert json.loads(capsys.readouterr().out)["passed"] is False
    assert_no_side_effects(offline)


def test_source_crlf_comparison_keeps_distinct_disk_hash(offline):
    """Only Git comparison normalizes newlines; raw disk evidence must remain raw."""
    name = "src/academic_agent/report_evidence_stage_qwen_canary.py"
    raw = offline["committed"][name].replace(b"\n", b"\r\n")
    (offline["repo"] / name).write_bytes(raw)
    identity = canary.verify_identity(COMMIT, canary.FIXTURE_SHA256)
    assert identity["disk_sha256"][name] == hashlib.sha256(raw).hexdigest()
    assert identity["disk_sha256"][name] != identity["committed_sha256"][name]
    assert_no_side_effects(offline)


def test_fixture_crlf_is_still_a_raw_identity_change(offline):
    """Git-equivalent newlines do not authorize different frozen fixture bytes."""
    path = offline["repo"] / canary.FIXTURE
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    with pytest.raises(canary.CanaryStopped, match="fixture_identity_mismatch"):
        canary.verify_identity(COMMIT, canary.FIXTURE_SHA256)
    assert_no_side_effects(offline)


@pytest.mark.parametrize("name", ["httpx", "httpcore", "anyio", "pydantic", "pydantic-core", "typing-extensions"])
def test_installed_dependency_drift_blocks_cli(offline, name):
    """Installed direct and transitive versions must match the committed lock."""
    offline["versions"][name] = "0.0.0-invalid"
    assert cli.main(arguments(offline, paid=True)) == 1
    assert_no_side_effects(offline)


def test_missing_installed_dependency_fails_closed(offline, monkeypatch, capsys):
    """Missing distribution metadata is unavailable, not a guessed compatible version."""
    def missing(_name):
        raise PackageNotFoundError("sensitive local metadata")
    monkeypatch.setattr(canary, "version", missing)
    assert cli.main(arguments(offline, paid=True)) == 1
    assert "sensitive local" not in capsys.readouterr().out
    assert_no_side_effects(offline)


def test_git_reader_has_only_bounded_read_arguments(offline, monkeypatch):
    """The identity plumbing never shells out or requests a checkout/index update."""
    calls = []
    def invoke(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(stdout=b"blob")
    monkeypatch.setattr(canary, "subprocess", SimpleNamespace(run=invoke))
    assert REAL_GIT("show", COMMIT + ":.gitattributes") == b"blob"
    assert calls == [(["git", "show", COMMIT + ":.gitattributes"], {
        "cwd": offline["repo"], "capture_output": True, "check": True, "timeout": 10})]


@pytest.mark.parametrize("defect", ["object", "extra", "missing", "order", "bool", "text", "origin", "empty"])
def test_flat_fixture_schema_is_strict_even_with_matching_test_hash(offline, monkeypatch, defect):
    """Hash binding does not substitute for a strict fixed flat-list contract."""
    path = offline["repo"] / canary.FIXTURE
    cases = read_json(path)
    if defect == "object":
        cases = {"cases": cases}
    elif defect == "extra":
        cases[0]["url"] = "https://example.invalid"
    elif defect == "missing":
        del cases[0]["question"]
    elif defect == "order":
        cases.reverse()
    elif defect == "bool":
        cases[0]["question"] = True
    elif defect == "text":
        cases[1]["summary"] = "Invented sales"
    elif defect == "origin":
        cases[1]["origin"] = "abstract"
    else:
        cases[0]["summary"] = ""
    raw = json.dumps(cases).encode()
    path.write_bytes(raw)
    monkeypatch.setattr(canary, "FIXTURE_SHA256", hashlib.sha256(raw).hexdigest())
    with pytest.raises(canary.CanaryStopped, match="fixture_invalid_or_unavailable"):
        canary.load_cases()
    assert_no_side_effects(offline)


def test_fixture_and_configuration_are_new_and_fixed(offline):
    """The new fixture and stage choices cannot inherit the old FQ allowance."""
    cases = canary.load_cases()
    assert [(row["case_id"], row["source_id"]) for row in cases] == [("SQ01", "A7"), ("SQ02", "M4")]
    assert cases[0]["summary"] == ("The synthetic ceramic strain gauge measured 32 microstrain in a bench fixture. "
                                    "No outdoor durability testing was performed.")
    assert cases[1]["summary"] is None and cases[1]["origin"] == "unknown"
    config = canary.configuration()
    assert config["model"] == "qwen3.5-plus"
    assert config["endpoint"] == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    assert config["max_requests"] == 6 and config["usd_soft_limit"] == "0.10"
    assert config["max_turns_per_case"] == 3 and config["max_tool_attempts_per_case"] == 2
    assert config["reservation_usd"] == "0.011149312"
    assert config["input_rate_per_million"] == "0.573" and config["output_rate_per_million"] == "3.44"
    assert config["price_scope"] == "frozen_conservative_estimate_not_invoice"
    assert config["tool_choice_by_stage"] == {"initial": "auto", "read": "auto", "final": "none"}
    assert config["final_tools_wire"] == "omitted" and "tool_choice" not in config
    assert config["credential_source"] == "process_DASHSCOPE_API_KEY_only"
    assert_no_side_effects(offline)


@pytest.mark.parametrize("mode", ["old_ack", "no_output", "no_ack", "abbrev", "secret", "dotenv", "resume"])
def test_cli_rejects_incomplete_or_legacy_authority_without_echo(offline, capsys, mode):
    """No dotenv, old protocol, argument abbreviation, secret flag or resume path exists."""
    args = arguments(offline)
    if mode == "old_ack":
        args += ["--authorize-paid", "report_evidence_followup_qwen", "--output-dir", str(offline["output"])]
    elif mode == "no_output":
        args += ["--authorize-paid", canary.PROTOCOL_IDENTITY]
    elif mode == "no_ack":
        args += ["--output-dir", str(offline["output"])]
    else:
        flag = {"abbrev": "--authorize", "secret": "--api-key", "dotenv": "--key-from-dotenv", "resume": "--resume"}[mode]
        args += [flag, KEY]
    if mode in {"abbrev", "secret", "dotenv", "resume"}:
        with pytest.raises(SystemExit) as exc:
            cli.main(args)
        assert exc.value.code == 2
    else:
        assert cli.main(args) == 1
    captured = capsys.readouterr()
    assert KEY not in captured.out + captured.err
    assert_no_side_effects(offline)


@pytest.mark.parametrize("key", [None, "", "has whitespace"], ids=["missing", "empty", "space"])
def test_invalid_dedicated_key_does_not_fallback_or_create_output(offline, capsys, key):
    """After preflight only the dedicated process key may be read, never another key."""
    offline["key"] = key
    assert cli.main(arguments(offline, paid=True)) == 1
    assert "invalid_dedicated_key" in capsys.readouterr().out
    assert offline["key_reads"] == ["DASHSCOPE_API_KEY"] and not offline["requests"]
    assert not offline["output"].exists()


@pytest.mark.parametrize("kind", ["occupied", "outside", "root", "parent"])
def test_invalid_output_precedes_key_and_preserves_existing_bytes(offline, kind):
    """An acknowledgement cannot overwrite/resume a batch or choose another tree."""
    sentinel = None
    if kind == "occupied":
        offline["output"].mkdir()
        sentinel = offline["output"] / "existing.txt"
        sentinel.write_bytes(b"preserve me")
    elif kind == "outside":
        offline["output"] = offline["repo"].parent / "outside"
    elif kind == "root":
        offline["output"] = offline["repo"] / "outputs"
    else:
        offline["output"] = offline["output"] / "missing" / "batch"
    assert cli.main(arguments(offline, paid=True)) == 1
    assert not offline["key_reads"] and not offline["requests"]
    if sentinel:
        assert sentinel.read_bytes() == b"preserve me"


def test_output_junction_metadata_is_rejected_before_key(offline, monkeypatch):
    """Windows junction metadata is rejected without needing symlink creation rights."""
    original = Path.lstat
    parent = offline["repo"] / "outputs"
    def inspect(path, *args, **kwargs):
        if path == parent:
            return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "lstat", inspect)
    assert cli.main(arguments(offline, paid=True)) == 1
    assert_no_side_effects(offline)


@pytest.mark.parametrize("lookup", [False, True], ids=["direct", "lookup"])
def test_cli_real_policy_tools_http_journal_summary(offline, capsys, lookup):
    """Both controls must traverse real tools and wire bytes, not a mocked case result."""
    offline["handler"] = provider(lookup)
    assert cli.main(arguments(offline, paid=True)) == 0
    summary = json.loads(capsys.readouterr().out)
    count = 6 if lookup else 4
    assert summary == read_json(offline["output"] / "summary.json")
    assert summary["passed"] is True and summary["request_count"] == count
    assert summary["unrun_cases"] == [] and summary["unknown_usage_requests"] == 0
    assert summary["semantic_support"] == "not_assessed" and summary["answer_verification"] == "not_verified"
    assert summary["summary_persisted"] is True
    assert summary["budget_consumed_usd"] == str(Decimal("0.011149312") * count)
    assert offline["key_reads"] == ["DASHSCOPE_API_KEY"]
    assert len(offline["requests"]) == len(offline["intents"]) == count
    assert [name for name, _args in offline["tools"]] == (["lookup_sources", "read_source"] * 2 if lookup
                                                         else ["read_source"] * 2)
    disk_events = events(offline["output"])
    assert [event["event"] for event in disk_events] == ["request_reserved", "request_finished"] * count
    for index, (request, intent, setup) in enumerate(zip(offline["requests"], offline["intents"],
                                                        offline["setup_at_dispatch"], strict=True)):
        body = json.loads(request.content)
        assert intent["event"] == "request_reserved" and intent["request_id"] == index + 1
        assert intent["request_sha256"] == hashlib.sha256(request.content).hexdigest()
        assert intent["request"] == body and intent["usage_status"] == "unknown"
        finished = disk_events[index * 2 + 1]
        assert finished["reported_usage"] == USAGE and finished["protocol_accepted"] is True
        assert finished["response_model_matches_authorized"] is True
        assert str(request.url) == canary.configuration()["endpoint"] and request.method == "POST"
        assert request.headers["Authorization"] == "Bearer " + KEY
        assert body["model"] == "qwen3.5-plus" and body["max_tokens"] == 512
        assert body["stream"] is body["enable_thinking"] is body["parallel_tool_calls"] is False
        if body["tool_choice"] == "none":
            assert "tools" not in body
            result = json.loads(body["messages"][-1]["content"])
            assert result["status"] in {"ok", "missing_text"}
        elif len(body["tools"]) == 1:
            ids = body["tools"][0]["function"]["parameters"]["properties"]["source_id"]["enum"]
            assert ids == (["A7"] if index < count // 2 else ["M4"])
        for previous, message in zip(body["messages"], body["messages"][1:], strict=False):
            if message["role"] == "tool":
                assert message["tool_call_id"] == previous["tool_calls"][0]["id"]
        assert setup["manifest.json"]["scope"] == "offline_contract_no_live_authorization"
        assert setup["manifest.json"]["live_authorization"] is False
        assert setup["manifest.json"]["configuration"] == stage_configuration()
        auth = setup["authorization.json"]
        assert auth["protocol_identity"] == canary.PROTOCOL_IDENTITY
        assert auth["independent_user_consent_verified"] is False and auth["old_allowance_reused"] is False
        assert auth["expected_commit"] == COMMIT and auth["expected_fixture_sha256"] == canary.FIXTURE_SHA256
        assert auth["identity_sha256"] == hashlib.sha256(canary._encoded(setup["identity.json"])).hexdigest()
    assert all(options == {"retries": 0, "verify": True, "trust_env": False} for options in offline["http_options"])
    assert all(options["follow_redirects"] is False and options["verify"] is True for options in offline["clients"])
    positive = read_json(offline["output"] / "SQ01.json")
    negative = read_json(offline["output"] / "SQ02.json")
    assert positive["result"]["state"] == "answered_with_evidence"
    assert positive["result"]["served_evidence"][0]["text"] == canary.load_cases()[0]["summary"]
    assert positive["result"]["evidence_ids"] == positive["result"]["audit"]["forwarded_read_ids"]
    assert positive["narrow_content_control"] == "requires_parent_review"
    assert negative["result"]["state"] == "abstained" and not negative["result"]["served_evidence"]
    assert negative["result"]["audit"]["tool_results"][-1]["status"] == "missing_text"
    assert {path.name for path in offline["output"].iterdir()} == {
        "manifest.json", "identity.json", "authorization.json", "events.jsonl", "SQ01.json", "SQ02.json", "summary.json"}
    assert all(KEY not in path.read_text(encoding="utf-8") for path in offline["output"].iterdir())


def test_first_core_failure_suppresses_actual_second_case_http(offline):
    """A transport-accepted invalid final must prevent even SQ02's first HTTP request."""
    ordinary = provider()
    def handle(request):
        if "annual sales" in json.loads(request.content)["messages"][1]["content"]:
            return ordinary(request)
        return response(payload({"role": "assistant", "content": "not JSON"}))
    offline["handler"] = handle
    summary = batch(offline)
    assert len(offline["requests"]) == 1
    assert all("annual sales" not in json.loads(request.content)["messages"][1]["content"] for request in offline["requests"])
    assert not summary["passed"] and summary["unrun_cases"] == ["SQ02"]
    assert summary["stop_reason"] == "policy_core_failed"
    assert summary["unknown_usage_requests"] == 0 and Decimal(summary["known_usage_estimated_usd"]) > 0
    assert read_json(offline["output"] / "SQ01.json")["result"]["audit"]["core"]["terminal_reason"] == "invalid_final_envelope"
    assert not (offline["output"] / "SQ02.json").exists()


@pytest.mark.parametrize("defect", ["wrong_model", "missing_usage", "bad_usage", "unknown_id", "no_tool",
                                   "abstain", "lookup_empty", "short_read", "uncited", "forged", "final_tool"])
def test_first_case_failure_never_becomes_positive_or_repair(offline, defect):
    """Rejected transport/policy/core/case outcomes remain distinct from a passed read."""
    ordinary = provider()
    def handle(request):
        body = json.loads(request.content)
        last = body["messages"][-1]
        if defect == "wrong_model":
            return response(payload(final(), model="qwen3.5-plus-other"))
        if defect == "missing_usage":
            return response(payload(final(), usage=None))
        if defect == "bad_usage":
            return response(payload(final(), usage={**USAGE, "total_tokens": 121}))
        if defect == "unknown_id":
            return response(payload(native_read("A8")))
        if defect == "no_tool":
            return response(payload(final()))
        if defect == "abstain":
            return response(payload(final(status="abstained")))
        if defect == "lookup_empty":
            message = (native_call("lookup_sources", {"query": "no matching record"}, "empty_lookup")
                       if last["role"] != "tool" else final(status="abstained"))
            return response(payload(message))
        if defect == "short_read" and last["role"] != "tool":
            return response(payload(native_read(length=10)))
        if last["role"] == "tool":
            if defect == "uncited":
                return response(payload(final()))
            if defect == "forged":
                return response(payload(final(["ev_invented"])))
            if defect == "final_tool":
                return response(payload(native_read(call_id="extra_read")))
        return ordinary(request)
    offline["handler"] = handle
    summary = batch(offline)
    count = 2 if defect in {"lookup_empty", "short_read", "uncited", "forged", "final_tool"} else 1
    assert len(offline["requests"]) == count
    assert summary["passed"] is False and summary["unrun_cases"] == ["SQ02"]
    assert summary["unknown_usage_requests"] == (1 if defect in {"missing_usage", "bad_usage"} else 0)
    if defect not in {"missing_usage", "bad_usage"}:
        assert Decimal(summary["known_usage_estimated_usd"]) > 0
    assert all("annual sales" not in json.loads(request.content)["messages"][1]["content"] for request in offline["requests"])


@pytest.mark.parametrize("defect", ["early", "empty_lookup", "answered", "refusal"])
def test_missing_text_case_requires_read_delivery_and_structured_abstention(offline, defect):
    """SQ02 cannot pass from lookup metadata, no tool, unstructured refusal or an answer."""
    ordinary = provider()
    def handle(request):
        body = json.loads(request.content)
        if "annual sales" not in body["messages"][1]["content"]:
            return ordinary(request)
        if defect == "early":
            return response(payload(final(status="abstained")))
        if defect == "empty_lookup":
            message = (native_call("lookup_sources", {"query": "nothing matches"}, "empty_negative")
                       if body["messages"][-1]["role"] != "tool" else final(status="abstained"))
            return response(payload(message))
        if body["messages"][-1]["role"] == "tool":
            return response(payload(final() if defect == "answered" else {"role": "assistant", "refusal": "Cannot answer"}))
        return ordinary(request)
    offline["handler"] = handle
    summary = batch(offline)
    assert summary["cases"][0]["passed"] is True and summary["cases"][1]["passed"] is False
    assert not summary["passed"] and summary["unrun_cases"] == []
    assert len(offline["requests"]) == (3 if defect == "early" else 4)


@pytest.mark.parametrize("filename", ["manifest.json", "events.jsonl", "identity.json", "authorization.json"])
def test_setup_write_failure_prevents_http(offline, monkeypatch, capsys, filename):
    """Every setup file is durable before the first possible HTTP request."""
    original = Path.open
    def fail(path, mode="r", *args, **kwargs):
        if path == offline["output"] / filename and mode == "xb":
            raise OSError("private setup detail " + KEY)
        return original(path, mode, *args, **kwargs)
    monkeypatch.setattr(Path, "open", fail)
    assert cli.main(arguments(offline, paid=True)) == 1
    assert not offline["requests"] and not offline["tools"]
    assert KEY not in capsys.readouterr().out


@pytest.mark.parametrize("filename", ["SQ01.json", "summary.json"])
def test_result_write_failure_retains_observed_usage(offline, monkeypatch, filename):
    """Failed publication is not success or free work, and SQ01 failure stops SQ02."""
    offline["handler"] = provider()
    original = Path.open
    def fail(path, mode="r", *args, **kwargs):
        if path == offline["output"] / filename and mode == "xb":
            raise OSError("cannot publish")
        return original(path, mode, *args, **kwargs)
    monkeypatch.setattr(Path, "open", fail)
    summary = batch(offline)
    assert not summary["passed"] and summary["stop_reason"] == "persistence_failed"
    assert summary["unknown_usage_requests"] == 0 and Decimal(summary["known_usage_estimated_usd"]) > 0
    assert len(offline["requests"]) == (2 if filename == "SQ01.json" else 4)
    assert summary["summary_persisted"] is (filename != "summary.json")
    assert summary["unrun_cases"] == (["SQ02"] if filename == "SQ01.json" else [])


@pytest.mark.parametrize("phase", ["reserve", "finish"])
def test_journal_failure_stops_batch_and_preserves_received_usage(offline, monkeypatch, phase):
    """A failed finish keeps memory usage; a failed reservation never reaches HTTP."""
    offline["handler"] = provider()
    original = Path.open
    def fail(path, mode="r", *args, **kwargs):
        if path == offline["output"] / "events.jsonl" and mode == "r+b":
            if phase == "reserve" or offline["requests"]:
                raise OSError("journal unavailable")
        return original(path, mode, *args, **kwargs)
    monkeypatch.setattr(Path, "open", fail)
    summary = batch(offline)
    assert not summary["passed"] and summary["stop_reason"] == "persistence_failed"
    assert summary["unrun_cases"] == ["SQ02"]
    assert len(offline["requests"]) == (0 if phase == "reserve" else 1)
    if phase == "finish":
        assert summary["pending_request_id"] == 1
        assert summary["unknown_usage_requests"] == 0 and Decimal(summary["known_usage_estimated_usd"]) > 0


@pytest.mark.parametrize("phase", ["before", "during"])
def test_identity_loss_stops_later_dispatch_without_erasing_usage(offline, monkeypatch, phase):
    """Identity lost after setup or during HTTP cannot authorize a subsequent request."""
    ordinary = provider()
    original = canary._git
    heads = 0
    def git(*args):
        nonlocal heads
        if args[0] == "rev-parse":
            heads += 1
            if phase == "before" and heads >= 2:
                return b"b" * 40
        return original(*args)
    monkeypatch.setattr(canary, "_git", git)
    def handle(request):
        with (offline["repo"] / "src/academic_agent/report_evidence_stage_qwen_canary.py").open("ab") as stream:
            stream.write(b"\n# changed during response\n")
        return ordinary(request)
    offline["handler"] = handle
    summary = batch(offline)
    assert not summary["passed"] and summary["unrun_cases"] == ["SQ02"]
    assert len(offline["requests"]) == (0 if phase == "before" else 1)
    if phase == "during":
        assert summary["unknown_usage_requests"] == 0 and Decimal(summary["known_usage_estimated_usd"]) > 0


@pytest.mark.parametrize("field,value", [("protocol_accepted", False), ("response_model_matches_authorized", False),
                                         ("provider_response_received", False), ("usage_status", "unknown")],
                         ids=["protocol", "model", "received", "usage"])
def test_runner_inspects_ledger_not_only_final_result(offline, monkeypatch, field, value):
    """A valid policy/core final cannot mask an unsuccessful transport observation."""
    original = StageQwenLedger.finish
    def finish(ledger, ordinal, **kwargs):
        original(ledger, ordinal, **kwargs)
        ledger.records[ordinal - 1][field] = value
    monkeypatch.setattr(StageQwenLedger, "finish", finish)
    offline["handler"] = provider()
    summary = batch(offline)
    assert not summary["passed"] and summary["unrun_cases"] == ["SQ02"]
    assert summary["stop_reason"] == "transport_observation_failed"
    assert len(offline["requests"]) == 2


@pytest.mark.parametrize("defect", ["redirect", "timeout", "secret"])
def test_http_failures_stop_without_retry_or_secret_diagnostics(offline, capsys, defect):
    """Network-shaped failures use only synthetic responses and never attempt repair."""
    def handle(request):
        if defect == "redirect":
            return response({}, status=307, headers={"Location": "https://example.invalid/forbidden"})
        if defect == "timeout":
            raise httpx.ReadTimeout("private failure " + KEY)
        return response(payload(final(answer="key=" + KEY)))
    offline["handler"] = handle
    assert cli.main(arguments(offline, paid=True)) == 1
    summary = json.loads(capsys.readouterr().out)
    assert summary["unrun_cases"] == ["SQ02"] and len(offline["requests"]) == 1
    assert summary["unknown_usage_requests"] == (0 if defect == "secret" else 1)
    assert KEY not in json.dumps(summary)
    assert all(KEY not in path.read_text(encoding="utf-8") for path in offline["output"].iterdir())
