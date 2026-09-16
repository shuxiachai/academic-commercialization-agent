"""CQ runner controls at the real catalog/executor/HTTP/journal boundary."""

import ast
from copy import deepcopy
from decimal import Decimal
import hashlib
from importlib.metadata import PackageNotFoundError
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from types import SimpleNamespace
import tomllib

import httpx
import pytest

import report_evidence_catalog_canary as cli
from academic_agent import report_evidence_catalog_qwen_canary as canary
from academic_agent.report_evidence_final_json_qwen_canary import _publish_result as frozen_publish

KEY = "sk-cq-offline-invented-not-a-credential"
COMMIT = "a" * 40
USAGE = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
REAL_ROOT = canary.ROOT
REAL_GIT = canary._git
SETUP = ("manifest.json", "identity.json", "experiment_manifest.json", "authorization.json")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def events(output):
    return [json.loads(line) for line in (output / "events.jsonl").read_text(encoding="utf-8").splitlines()]


def final(ids=(), *, status="answered", answer="Synthetic answer"):
    return {"role": "assistant", "content": json.dumps({
        "answer": answer, "status": status, "evidence_ids": list(ids)})}


def native(source_id="A6", *, offset=0, length=1500, call_id="native_read"):
    return {"role": "assistant", "content": None, "tool_calls": [{
        "id": call_id, "type": "function", "function": {"name": "read_source", "arguments": json.dumps({
            "source_id": source_id, "offset": offset, "length": length})}}]}


def payload(message, **changes):
    return {"model": "qwen3.5-plus", "usage": deepcopy(USAGE), "choices": [{
        "index": 0, "message": message, "finish_reason": "tool_calls" if message.get("tool_calls") else "stop",
    }], **changes}


def response(value, *, status=200, headers=None):
    raw = value if isinstance(value, bytes) else json.dumps(value).encode("utf-8")
    return httpx.Response(status, stream=httpx.ByteStream(raw), headers=headers)


def provider(request):
    """Never invent receipts: answer only from the actual serialized local result."""
    body = json.loads(request.content)
    negative = "annual revenue" in body["messages"][1]["content"]
    last = body["messages"][-1]
    if last["role"] != "tool":
        # Reusing this ID in the OTHER conversation is legal and tests new state.
        return response(payload(native("M6" if negative else "A6")))
    delivered = json.loads(last["content"])
    return response(payload(final(status="abstained", answer="Saved text is unavailable; I abstain.") if negative
                            else final([delivered["evidence_id"]], answer=
                                       "24 kHz at 60% relative humidity; no outdoor deployment or long-term study.")))


@pytest.fixture(autouse=True)
def offline(tmp_path, monkeypatch):
    """Public-input copies, fake key lookup, real wrapper/adapter, intercepted HTTP."""
    repo = tmp_path / "repo"
    committed = {}
    for name in canary.IDENTITY_PATHS:
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REAL_ROOT / name, target)
        committed[name] = target.read_bytes().replace(b"\r\n", b"\n")
    (repo / "outputs").mkdir()
    versions = {row["name"]: row["version"] for row in tomllib.loads(
        (repo / "uv.lock").read_text(encoding="utf-8"))["package"]}
    state = {"repo": repo, "committed": committed, "versions": versions, "git": [], "key_reads": [],
             "requests": [], "intents": [], "setup": [], "handler": provider,
             "http_options": [], "client_options": [], "output": repo / "outputs" / "batch"}

    def git(*args):
        state["git"].append(args)
        if args[0] == "rev-parse":
            return COMMIT.encode() + b"\n"
        if args[0] == "status":
            return b""
        if args[0] == "show":
            revision, name = args[1].split(":", 1)
            assert revision == COMMIT
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
        state["setup"].append({name: read_json(state["output"] / name) for name in SETUP})
        return state["handler"](request)

    def transport(**kwargs):
        state["http_options"].append(kwargs)
        return httpx.MockTransport(dispatch)

    def client(**kwargs):
        state["client_options"].append(kwargs)
        # Preserve Windows Proactor socketpair; forbid real HTTP construction,
        # not the unrelated internal sockets needed by the event loop itself.
        if (not isinstance(kwargs.get("transport"), httpx.MockTransport)
                or kwargs.get("trust_env") is not False or kwargs.get("proxy") is not None or kwargs.get("mounts")):
            forbidden()
        return real_client(**kwargs)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", transport)
    monkeypatch.setattr(httpx, "AsyncClient", client)
    monkeypatch.setattr(httpx, "HTTPTransport", forbidden)
    monkeypatch.setattr(httpx, "Client", forbidden)
    return state


def arguments(state, *, paid=False):
    args = ["--expected-commit", COMMIT, "--expected-fixture-sha256", canary.FIXTURE_SHA256]
    if paid:
        args += ["--authorize-paid", canary.PROTOCOL_IDENTITY, "--output-dir", str(state["output"])]
    return args


def batch(state):
    return canary.run_canary(expected_commit=COMMIT, expected_fixture_sha256=canary.FIXTURE_SHA256,
                             authorize_paid=canary.PROTOCOL_IDENTITY, output_dir=state["output"])


def no_effects(state):
    assert not state["key_reads"] and not state["requests"]
    assert list((state["repo"] / "outputs").iterdir()) == []


def test_default_cli_is_identity_only(offline, capsys):
    """The successful default returns before key lookup, ledger construction or HTTP."""
    assert cli.main(arguments(offline)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["mode"] == "identity_only" and result["identity_verified"] is True
    assert result["live_authorized"] is False
    identity = result["identity"]
    assert set(identity["disk_sha256"]) == set(identity["committed_sha256"]) == set(canary.IDENTITY_PATHS)
    assert identity["configuration_sha256"] == hashlib.sha256(canary._encoded(canary.configuration())).hexdigest()
    assert all(("show", COMMIT + ":" + name) in offline["git"] for name in canary.IDENTITY_PATHS)
    no_effects(offline)


def test_imports_do_not_read_credentials_dotenv_create_output_or_construct_http(offline):
    """Fresh-process imports, not already-cached modules, must have no live side effects."""
    script = r'''
import builtins, os, pathlib, socket, sys
import httpx
def blocked(*args, **kwargs):
    raise AssertionError("forbidden import side effect")
original_open = builtins.open
def opened(path, *args, **kwargs):
    if isinstance(path, (str, bytes, os.PathLike)) and pathlib.Path(path).name == ".env":
        blocked()
    return original_open(path, *args, **kwargs)
builtins.open = opened
original_get = os._Environ.get
def getenv(self, name, *args):
    if "KEY" in name or name.startswith("DASHSCOPE") or name.startswith("OPENAI"):
        blocked()
    return original_get(self, name, *args)
os._Environ.get = getenv
pathlib.Path.mkdir = blocked
httpx.AsyncClient = httpx.Client = blocked
socket.create_connection = blocked
import report_evidence_catalog_canary
assert "dotenv" not in sys.modules
print("import_only_no_effects")
'''
    env = {name: os.environ[name] for name in ("SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP") if name in os.environ}
    env["PYTHONPATH"] = os.pathsep.join((str(REAL_ROOT), str(REAL_ROOT / "src")))
    process = subprocess.run([sys.executable, "-B", "-c", script], cwd=REAL_ROOT, env=env,
                             capture_output=True, text=True, check=False, timeout=30)
    assert process.returncode == 0, process.stderr
    assert process.stdout.strip() == "import_only_no_effects"
    no_effects(offline)


@pytest.mark.parametrize("name", canary.IDENTITY_PATHS)
def test_every_bound_disk_file_is_checked_despite_clean_status(offline, capsys, name):
    """Status-hidden edits in ANY executing dependency or frozen CQ input block setup."""
    path = offline["repo"] / name
    path.write_bytes(path.read_bytes() + b"\n# hidden drift\n")
    assert cli.main(arguments(offline, paid=True)) == 1
    assert json.loads(capsys.readouterr().out)["error"] == "committed_content_mismatch"
    no_effects(offline)


@pytest.mark.parametrize("defect", ["commit", "sha_shape", "fixture_authority", "git_failure", "dirty",
                                  "blob", "missing_file", "attributes", "fixture_bytes", "versions", "missing_package"])
def test_identity_failures_precede_key_output_and_http(offline, monkeypatch, capsys, defect):
    """Each identity component fails closed before the live path's first side effect."""
    args = arguments(offline, paid=True)
    git = canary._git
    if defect == "commit":
        args[1] = "b" * 40
    elif defect == "sha_shape":
        args[1] = "HEAD"
    elif defect == "fixture_authority":
        args[3] = "0" * 64
    elif defect in {"git_failure", "dirty"}:
        def changed(*items):
            if defect == "git_failure":
                raise subprocess.CalledProcessError(1, ["git"], stderr=KEY)
            return b" M tracked" if items[0] == "status" else git(*items)
        monkeypatch.setattr(canary, "_git", changed)
    elif defect == "blob":
        offline["committed"][canary.PROTOCOL] += b"drift"
    elif defect == "missing_file":
        (offline["repo"] / canary.PROTOCOL).unlink()
    elif defect in {"attributes", "fixture_bytes"}:
        name = ".gitattributes" if defect == "attributes" else canary.FIXTURE
        path = offline["repo"] / name
        raw = b"* text=auto\n" if defect == "attributes" else path.read_bytes() + b"\n"
        path.write_bytes(raw)
        offline["committed"][name] = raw.replace(b"\r\n", b"\n")
    elif defect == "versions":
        offline["versions"]["httpx"] = "0.0.0"
    else:
        def unavailable(name):
            raise PackageNotFoundError(name)
        monkeypatch.setattr(canary, "version", unavailable)
    assert cli.main(args) == 1
    assert KEY not in capsys.readouterr().out
    no_effects(offline)


def test_source_lf_comparison_preserves_raw_disk_hash(offline):
    """LF blob normalization is not permission to normalize the fixture's raw hash."""
    name = "src/academic_agent/report_evidence_catalog_qwen_canary.py"
    path = offline["repo"] / name
    raw = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    path.write_bytes(raw)
    identity = canary.verify_identity(COMMIT, canary.FIXTURE_SHA256)
    assert identity["disk_sha256"][name] == hashlib.sha256(raw).hexdigest()
    assert identity["disk_sha256"][name] != identity["committed_sha256"][name]
    fixture = offline["repo"] / canary.FIXTURE
    fixture.write_bytes(fixture.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    with pytest.raises(canary.CanaryStopped, match="fixture_identity_mismatch"):
        canary.verify_identity(COMMIT, canary.FIXTURE_SHA256)
    no_effects(offline)


def test_executing_import_closure_is_bound_and_publisher_is_directly_reused(offline):
    """Imported helper modules execute too; a coupling list alone must not omit them."""
    assert canary._publish_result is frozen_publish
    pending = ["src/academic_agent/report_evidence_catalog_qwen_canary.py", "report_evidence_catalog_canary.py"]
    seen = set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        assert name in canary.IDENTITY_PATHS
        tree = ast.parse((REAL_ROOT / name).read_text(encoding="utf-8"))
        for node in tree.body:
            # Only imports that execute here; TYPE_CHECKING-only SourceCollection
            # annotations do not import the production retrieval pipeline.
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            modules = (["academic_agent." + alias.name for alias in node.names]
                       if node.module == "academic_agent" else [node.module])
            for module in modules:
                if module.startswith("academic_agent."):
                    dependency = "src/" + module.replace(".", "/") + ".py"
                    pending.append(dependency)
    assert "src/academic_agent/report_evidence_final_json_qwen_transport.py" in seen
    assert "src/academic_agent/report_evidence_guarded_followup.py" in seen
    assert "src/academic_agent/__init__.py" in canary.IDENTITY_PATHS
    assert {canary.FIXTURE, canary.PROTOCOL, "pyproject.toml", "uv.lock", ".gitattributes"} <= set(canary.IDENTITY_PATHS)


def test_git_reader_is_read_only_bounded_and_does_not_refresh_index(offline, monkeypatch):
    """The implementation uses no shell, index refresh, checkout or unrestricted scan."""
    seen = []
    def invoke(command, **kwargs):
        seen.append((command, kwargs))
        return SimpleNamespace(stdout=b"ok")
    monkeypatch.setattr(canary, "subprocess", SimpleNamespace(run=invoke))
    assert REAL_GIT("show", COMMIT + ":" + canary.PROTOCOL) == b"ok"
    command, options = seen[0]
    assert command == ["git", "--no-optional-locks", "show", COMMIT + ":" + canary.PROTOCOL]
    assert options == {"cwd": offline["repo"], "capture_output": True, "check": True, "timeout": 10}


@pytest.mark.parametrize("defect", ["extra", "case_order", "target", "five", "source_order", "url", "doi",
                                  "positive_absent", "negative_present", "long_title", "publisher", "question"])
def test_fixture_shape_rejected_even_with_matching_test_hash(offline, monkeypatch, defect):
    """Fixed labels, six ordered sources and absent metadata are independently checked."""
    cases = canary.load_cases()
    if defect == "extra":
        cases[0]["expected_answer"] = "not input"
    elif defect == "case_order":
        cases.reverse()
    elif defect == "target":
        cases[0]["target_source_id"] = "A1"
    elif defect == "five":
        cases[0]["sources"].pop(0)
    elif defect == "source_order":
        cases[0]["sources"].reverse()
    elif defect in {"url", "doi"}:
        cases[0]["sources"][0][defect] = "synthetic locator"
    elif defect == "positive_absent":
        cases[0]["sources"][5]["summary"] = None
    elif defect == "negative_present":
        cases[1]["sources"][5]["summary"] = "Invented revenue"
    elif defect == "long_title":
        cases[0]["sources"][0]["title"] = "x" * 257
    elif defect == "publisher":
        cases[0]["sources"][0]["publisher"] = "Not synthetic"
    else:
        cases[0]["question"] = ""
    raw = canary._encoded(cases)
    (offline["repo"] / canary.FIXTURE).write_bytes(raw)
    monkeypatch.setattr(canary, "FIXTURE_SHA256", hashlib.sha256(raw).hexdigest())
    with pytest.raises(canary.CanaryStopped, match="fixture_invalid_or_unavailable"):
        canary.load_cases()
    no_effects(offline)


@pytest.mark.parametrize("mode", ["output_only", "legacy", "no_output", "key_argument", "abbreviation"])
def test_cli_rejects_ambiguous_or_legacy_authority_without_echo(offline, capsys, mode):
    """No old acknowledgement, extra credential argument or partial flag buys a call."""
    args = arguments(offline)
    if mode == "output_only":
        args += ["--output-dir", str(offline["output"])]
    elif mode == "legacy":
        args += ["--authorize-paid", "report_evidence_final_json_qwen_canary_v1", "--output-dir", str(offline["output"])]
    elif mode == "no_output":
        args += ["--authorize-paid", canary.PROTOCOL_IDENTITY]
    else:
        args += ["--api-key" if mode == "key_argument" else "--authorize", KEY]
    if mode in {"key_argument", "abbreviation"}:
        with pytest.raises(SystemExit) as exc:
            cli.main(args)
        assert exc.value.code == 2
    else:
        assert cli.main(args) == 1
    captured = capsys.readouterr()
    assert KEY not in captured.out + captured.err
    no_effects(offline)


@pytest.mark.parametrize("key", [None, "", " has whitespace ", 123, "x" * 513])
def test_invalid_key_has_no_fallback_or_output(offline, capsys, key):
    """Only the fake process DASHSCOPE lookup is permitted; invalid values stop setup."""
    offline["key"] = key
    assert cli.main(arguments(offline, paid=True)) == 1
    assert json.loads(capsys.readouterr().out)["error"] == "invalid_dedicated_key"
    assert offline["key_reads"] == ["DASHSCOPE_API_KEY"] and not offline["requests"]
    assert not offline["output"].exists()


@pytest.mark.parametrize("kind", ["occupied", "outside", "outputs_root", "missing_parent", "junction"])
def test_output_admission_precedes_key_and_preserves_existing_data(offline, monkeypatch, kind):
    """An occupied/indirect/outside output is neither resumed nor silently relocated."""
    sentinel = None
    if kind == "occupied":
        offline["output"].mkdir()
        sentinel = offline["output"] / "sentinel"
        sentinel.write_bytes(b"preserve")
    elif kind == "outside":
        offline["output"] = offline["repo"] / "elsewhere"
    elif kind == "outputs_root":
        offline["output"] = offline["repo"] / "outputs"
    elif kind == "missing_parent":
        offline["output"] = offline["output"] / "child"
    else:
        original = Path.lstat
        def inspect(path, *args, **kwargs):
            if path == offline["repo"] / "outputs":
                return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
            return original(path, *args, **kwargs)
        monkeypatch.setattr(Path, "lstat", inspect)
    with pytest.raises(canary.CanaryStopped):
        batch(offline)
    assert not offline["key_reads"] and not offline["requests"]
    if sentinel is not None:
        assert sentinel.read_bytes() == b"preserve"


def test_real_wrapper_four_http_requests_sixth_targets_and_separate_authority(offline, capsys):
    """Two fresh conversations must share accounting and deliver actual executor receipts."""
    assert cli.main(arguments(offline, paid=True)) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["passed"] and summary["request_count"] == len(offline["requests"]) == 4
    assert summary["unrun_cases"] == [] and summary["unknown_usage_requests"] == 0
    assert summary["semantic_support"] == "not_assessed" and summary["answer_verification"] == "not_verified"
    assert Decimal(summary["budget_consumed_usd"]) == Decimal("0.044597248")
    assert read_json(offline["output"] / "summary.json") == summary
    finished = [event for event in events(offline["output"]) if event["event"] == "request_finished"]
    assert len(finished) == 4
    for index, (request, intent, record, setup) in enumerate(zip(
            offline["requests"], offline["intents"], finished, offline["setup"], strict=True)):
        body = json.loads(request.content)
        assert request.content == canary._encoded(body)
        assert intent["event"] == "request_reserved" and intent["request_id"] == index + 1
        assert intent["request_sha256"] == record["request_sha256"] == hashlib.sha256(request.content).hexdigest()
        assert record["request"] == intent["request"] == body
        assert record["reported_usage"] == USAGE and record["usage_status"] == "complete"
        assert record["provider_response_received"] and record["response_model_matches_authorized"]
        assert request.url == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer " + KEY
        assert request.headers["accept-encoding"] == "identity"
        assert body["model"] == "qwen3.5-plus" and body["max_tokens"] == 512
        assert body["temperature"] == 0 and body["enable_thinking"] is body["stream"] is body["parallel_tool_calls"] is False
        assert len(request.content) <= 12288 and b"target_source_id" not in request.content
        prefix = "A" if index < 2 else "M"
        catalog = json.loads(body["messages"][2]["content"])
        assert catalog["returned_count"] == catalog["total_count"] == 6 and catalog["coverage"] == "complete"
        assert [entry["source_id"] for entry in catalog["entries"]] == [prefix + str(n) for n in range(1, 7)]
        assert all(set(entry) == {"source_id", "title", "title_truncated"} for entry in catalog["entries"])
        if index % 2 == 0:
            assert len(body["messages"]) == 3 and body["tool_choice"] == "auto" and "response_format" not in body
            assert [tool["function"]["name"] for tool in body["tools"]] == ["read_source"]
            assert body["tools"][0]["function"]["parameters"]["properties"]["source_id"]["enum"] == [
                prefix + str(n) for n in range(1, 7)]
            assert b"shifted by 24" not in request.content
        else:
            assert body["tool_choice"] == "none" and "tools" not in body
            assert body["response_format"] == {"type": "json_object"}
            assert body["messages"][3] == finished[index - 1]["assistant_message"]
            tool = body["messages"][4]
            assert tool["tool_call_id"] == "native_read" and tool["role"] == "tool"
            delivered = json.loads(tool["content"])
            assert delivered["source_id"] == prefix + "6"
            assert delivered["status"] == ("ok" if index == 1 else "missing_text")
        assert setup["manifest.json"]["live_authorization"] is False
        assert setup["manifest.json"]["scope"] == "offline_contract_no_live_authorization"
        assert setup["manifest.json"]["configuration"]["max_requests"] == 6
        experiment, auth, identity = (setup[name] for name in SETUP[2:] + ("identity.json",))
        assert experiment["configuration"]["max_requests"] == auth["max_requests"] == 4
        assert experiment["scope"] == "parent_only_single_synthetic_live_batch"
        assert experiment["adapter_manifest_grants_live_authorization"] is False
        assert auth["independent_user_consent_verified"] is False and auth["parent_operator_only"] is True
        assert auth["old_allowance_reused"] is False and auth["standing_authorization_source"] == canary.PROTOCOL
        assert auth["expected_commit"] == COMMIT and auth["expected_fixture_sha256"] == canary.FIXTURE_SHA256
        assert auth["identity_sha256"] == hashlib.sha256(canary._encoded(identity)).hexdigest()
        assert auth["experiment_manifest_sha256"] == hashlib.sha256(canary._encoded(experiment)).hexdigest()
    for case_id in ("CQ01", "CQ02"):
        case = read_json(offline["output"] / (case_id + ".json"))
        audit = case["result"]["audit"]
        assert case["passed"] and case["narrow_content_control"] == "requires_parent_review"
        assert audit["core"]["tool_executions"] == audit["core"]["tool_attempts"] == 1
        assert audit["core"]["transport_turns"] == audit["downstream_calls"] == 2
    positive = read_json(offline["output"] / "CQ01.json")["result"]
    assert positive["state"] == "answered_with_evidence" and len(positive["served_evidence"]) == 1
    assert positive["evidence_ids"] == positive["audit"]["forwarded_read_ids"] == positive["audit"]["core"]["delivered_read_ids"]
    assert positive["served_evidence"][0]["text"] == canary.load_cases()[0]["sources"][5]["summary"]
    negative = read_json(offline["output"] / "CQ02.json")["result"]
    assert negative["state"] == "abstained" and negative["evidence_ids"] == negative["served_evidence"] == []
    assert offline["http_options"] == [{"retries": 0, "verify": True, "trust_env": False}] * 4
    assert all(options["follow_redirects"] is options["trust_env"] is False
               and options["verify"] is True and options["timeout"].connect == 10
               and options["timeout"].read == 60 for options in offline["client_options"])
    assert set(path.name for path in offline["output"].iterdir()) == {*SETUP, "events.jsonl", "CQ01.json", "CQ02.json", "summary.json"}


@pytest.mark.parametrize("defect", ["wrong_source", "partial", "offset", "early_abstain", "no_read_answer", "invisible",
                                  "lookup", "fenced_json", "prose", "bad_receipt", "empty_receipt", "final_tool"])
def test_positive_failure_stops_before_any_second_case_http(offline, defect):
    """No-read/wrong/partial/malformed successes must not buy a CQ02 request or repair."""
    def handle(request):
        body = json.loads(request.content)
        assert "annual revenue" not in body["messages"][1]["content"]
        initial = body["messages"][-1]["role"] != "tool"
        if initial:
            if defect in {"early_abstain", "no_read_answer"}:
                return response(payload(final(status="abstained" if defect == "early_abstain" else "answered")))
            message = native("A1" if defect == "wrong_source" else "A7" if defect == "invisible" else "A6",
                             offset=1 if defect == "offset" else 0, length=8 if defect == "partial" else 1500)
            if defect == "lookup":
                message["tool_calls"][0]["function"] = {"name": "lookup_sources", "arguments": '{"query":"ceramic"}'}
            return response(payload(message))
        delivered = json.loads(body["messages"][-1]["content"])
        message = final([delivered["evidence_id"]])
        if defect == "fenced_json":
            message["content"] = "```json\n" + message["content"] + "\n```"
        elif defect == "prose":
            message["content"] = "Answer: " + message["content"]
        elif defect == "bad_receipt":
            message = final(["A6"])
        elif defect == "empty_receipt":
            message = final()
        elif defect == "final_tool":
            message = native(call_id="second_read")
        return response(payload(message))
    offline["handler"] = handle
    summary = batch(offline)
    expected_calls = 1 if defect in {"early_abstain", "no_read_answer", "invisible", "lookup"} else 2
    # Observe dispatch count first: removing the runner's stop branch must go
    # red for the extra CQ02 HTTP request, not merely a different summary label.
    assert len(offline["requests"]) == expected_calls
    assert not summary["passed"] and summary["unrun_cases"] == ["CQ02"]
    assert 1 <= len(offline["requests"]) <= 2 and summary["request_count"] == len(offline["requests"])
    assert not (offline["output"] / "CQ02.json").exists()
    assert summary["unknown_usage_requests"] == 0 and summary["stop_reason"] is not None


@pytest.mark.parametrize("defect", ["early_abstain", "wrong_read", "answered", "invented_receipt"])
def test_missing_text_requires_actual_target_read_then_abstention(offline, defect):
    """Missing text cannot be inferred from the metadata or replaced by another record."""
    def handle(request):
        body = json.loads(request.content)
        if "annual revenue" not in body["messages"][1]["content"]:
            return provider(request)
        if body["messages"][-1]["role"] != "tool":
            if defect == "early_abstain":
                return response(payload(final(status="abstained")))
            return response(payload(native("M1" if defect == "wrong_read" else "M6")))
        if defect == "answered":
            return response(payload(final()))
        return response(payload(final(["M6"] if defect == "invented_receipt" else [], status="abstained")))
    offline["handler"] = handle
    summary = batch(offline)
    assert not summary["passed"] and summary["cases"][0]["passed"] and not summary["cases"][1]["passed"]
    assert len(offline["requests"]) == (3 if defect == "early_abstain" else 4)


@pytest.mark.parametrize("field", ["protocol_accepted", "provider_response_received", "response_model_matches_authorized",
                                 "usage_status", "case_id", "request_sha256", "tool_choice", "tools", "catalog",
                                 "native_id", "tool_pair", "text", "snapshot_hash", "missing_status"])
def test_gate_rejects_inconsistent_observation_before_next_http(offline, monkeypatch, field):
    """A plausible final result cannot override incompatible accounted wire evidence."""
    original = canary._case_gate
    def gate(case, snapshot, result, records, ledger):
        if field in {"protocol_accepted", "provider_response_received", "response_model_matches_authorized"}:
            records[-1][field] = False
        elif field == "usage_status":
            records[-1][field] = "unknown"
        elif field == "case_id":
            records[-1][field] = "OTHER"
        elif field == "request_sha256":
            records[-1][field] = "0" * 64
        else:
            body = records[-1]["request"]
            if field == "tool_choice":
                body["tool_choice"] = "auto"
            elif field == "tools":
                body["tools"] = []
            elif field == "catalog":
                body["messages"][2]["content"] = "{}"
            elif field == "native_id":
                records[0]["assistant_message"]["tool_calls"][0]["id"] = "unrelated"
            elif field == "tool_pair":
                body["messages"][4]["tool_call_id"] = "unrelated"
            else:
                delivered = json.loads(body["messages"][4]["content"])
                delivered[{"text": "text", "snapshot_hash": "snapshot_hash", "missing_status": "status"}[field]] = (
                    "missing_text" if field == "missing_status" else "changed")
                body["messages"][4]["content"] = json.dumps(delivered)
            records[-1]["request_sha256"] = hashlib.sha256(canary._encoded(body)).hexdigest()
        return original(case, snapshot, result, records, ledger)
    monkeypatch.setattr(canary, "_case_gate", gate)
    summary = batch(offline)
    assert not summary["passed"] and summary["unrun_cases"] == ["CQ02"]
    assert len(offline["requests"]) == 2


@pytest.mark.parametrize("case_first,expected", [(0, "runner_request_limit"), (4, "runner_request_limit")])
def test_runner_four_request_guard_blocks_fifth_actual_http(offline, case_first, expected):
    """A fresh adapter cannot spend the ledger's two remaining inherited slots."""
    identity = canary.verify_identity(COMMIT, canary.FIXTURE_SHA256)
    summary = batch(offline)
    assert summary["passed"] and len(offline["requests"]) == 4
    # Rebuild observed accounting in a same-type in-memory view only for this
    # guard test; do not invoke a second batch or touch its occupied output.
    ledger = object.__new__(canary.CatalogQwenLedger)
    ledger.output_dir = offline["output"]
    ledger.records = [event for event in events(offline["output"]) if event["event"] == "request_finished"]
    ledger.pending = ledger.stop_reason = None
    ledger.case_id = "CQ03_NOT_AUTHORIZED"
    case = canary.load_cases()[0]
    snapshot = canary.snapshot_for(case)
    fresh = canary.CatalogQwenFollowupTransport(KEY, ledger, snapshot=snapshot)
    checked = canary._CheckedTransport(fresh, ledger, identity, case_first)
    result = canary.run_catalog_followup(snapshot, case["question"], transport=checked)
    assert result.state == "failed" and ledger.stop_reason == expected
    assert len(offline["requests"]) == len(ledger.records) == 4


def test_runner_two_request_case_guard_independently_blocks_dispatch(offline):
    """The case cap is separate from both the fresh adapter and the four-call batch cap."""
    identity = canary.verify_identity(COMMIT, canary.FIXTURE_SHA256)
    case = canary.load_cases()[0]
    snapshot = canary.snapshot_for(case)
    ledger = canary.CatalogQwenLedger(offline["output"])
    # No HTTP is needed to exercise an already-accounted per-case cap.
    ledger.records = [{}, {}]
    transport = canary.CatalogQwenFollowupTransport(KEY, ledger, snapshot=snapshot)
    checked = canary._CheckedTransport(transport, ledger, identity, 0)
    result = canary.run_catalog_followup(snapshot, case["question"], transport=checked)
    assert result.state == "failed" and ledger.stop_reason == "runner_case_request_limit"
    assert not offline["requests"]


@pytest.mark.parametrize("phase", ["before_first", "after_first", "before_second", "after_second"])
def test_identity_drift_retains_usage_and_stops_next_dispatch(offline, monkeypatch, phase):
    """Post-response identity loss cannot erase cost or admit another paid attempt."""
    original = canary.verify_identity
    calls = []
    trigger = {"before_first": 2, "after_first": 3, "before_second": 4, "after_second": 5}[phase]
    def verify(*args):
        calls.append(1)
        identity = original(*args)
        if len(calls) == trigger:
            identity["runtime"]["python"] = "drift"
        return identity
    monkeypatch.setattr(canary, "verify_identity", verify)
    summary = batch(offline)
    expected = {"before_first": 0, "after_first": 1, "before_second": 1, "after_second": 2}[phase]
    assert not summary["passed"] and summary["stop_reason"] == "runtime_identity_changed"
    assert summary["request_count"] == len(offline["requests"]) == expected
    assert summary["unrun_cases"] == ["CQ02"] and summary["unknown_usage_requests"] == 0
    assert (Decimal(summary["known_usage_estimated_usd"]) > 0) is bool(expected)


@pytest.mark.parametrize("defect", ["unknown_usage", "contradictory_usage", "wrong_model", "http_error", "http_error_with_valid_usage", "redirect",
                                  "timeout", "oversize", "compressed", "secret", "escaped_secret"])
def test_transport_failures_preserve_first_usage_and_never_start_second_case(offline, capsys, defect):
    """Accounting/HTTP/privacy failures after a real read stop without retry or secret diagnostics."""
    def handle(request):
        if len(offline["requests"]) == 1:
            return provider(request)
        if defect == "timeout":
            raise httpx.ReadTimeout("private failure " + KEY)
        if defect == "oversize":
            return response(b"x" * (65536 + 1))
        if defect == "compressed":
            return response(b"bad", headers={"content-encoding": "gzip"})
        if defect == "http_error_with_valid_usage":
            # The frozen _post refuses status BEFORE parsing even valid usage.
            # Do not reinterpret response receipt as known accounting.
            return response(payload(final(status="abstained")), status=500)
        if defect in {"http_error", "redirect"}:
            return response(b"private " + KEY.encode(), status=500 if defect == "http_error" else 302)
        message = final(answer="Escaped: " + "".join(f"\\u{ord(char):04x}" for char in KEY)
                        if defect == "escaped_secret" else KEY if defect == "secret" else "Synthetic")
        value = payload(message)
        if defect == "unknown_usage":
            value.pop("usage")
        elif defect == "contradictory_usage":
            value["usage"]["total_tokens"] = 999
        elif defect == "wrong_model":
            value["model"] = "different-model"
        return response(value)
    offline["handler"] = handle
    assert cli.main(arguments(offline, paid=True)) == 1
    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert not summary["passed"] and summary["request_count"] == len(offline["requests"]) == 2
    assert summary["unrun_cases"] == ["CQ02"] and Decimal(summary["known_usage_estimated_usd"]) > 0
    unknown = defect not in {"wrong_model", "secret", "escaped_secret"}
    assert summary["unknown_usage_requests"] == int(unknown)
    assert summary["cost_coverage"] == ("lower_bound" if unknown else "complete_for_reported_requests")
    assert KEY not in captured.out + captured.err
    assert all(KEY not in path.read_text(encoding="utf-8") for path in offline["output"].iterdir())


@pytest.mark.parametrize("name", ["manifest.json", "events.jsonl", ".identity.json.pending",
                                 ".experiment_manifest.json.pending", ".authorization.json.pending"])
def test_setup_failure_prevents_all_http(offline, monkeypatch, capsys, name):
    """Every required setup file is durable before any request can be dispatched."""
    opened = Path.open
    def fail(path, *args, **kwargs):
        if path == offline["output"] / name:
            raise OSError("private setup " + KEY)
        return opened(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", fail)
    assert cli.main(arguments(offline, paid=True)) == 1
    assert not offline["requests"] and KEY not in capsys.readouterr().out


@pytest.mark.parametrize("phase", ["reserve", "finish"])
def test_journal_failure_preserves_uncertainty_and_stops_at_http_boundary(offline, monkeypatch, phase):
    """Failed reserve sends nothing; failed finish retains received usage with pending intent."""
    opened = Path.open
    count = []
    def fail(path, mode="r", *args, **kwargs):
        if path == offline["output"] / "events.jsonl" and mode == "r+b":
            count.append(1)
            if len(count) == (1 if phase == "reserve" else 2):
                raise OSError("private journal " + KEY)
        return opened(path, mode, *args, **kwargs)
    monkeypatch.setattr(Path, "open", fail)
    summary = batch(offline)
    assert not summary["passed"] and summary["stop_reason"] == "persistence_failed"
    assert len(offline["requests"]) == (0 if phase == "reserve" else 1)
    assert summary["unrun_cases"] == ["CQ02"]
    if phase == "finish":
        assert summary["pending_request_id"] == 1 and summary["unknown_usage_requests"] == 0
        assert Decimal(summary["known_usage_estimated_usd"]) > 0


@pytest.fixture
def publication_io(offline, monkeypatch):
    """Inject filesystem boundary faults, never monkeypatch a frozen runner/helper."""
    state = {"target": "summary.json", "fault": None, "steps": [], "fd": None, "at_sync": []}
    original_open, original_sync, original_link = Path.open, os.fsync, os.link
    def paths():
        return offline["output"] / state["target"], offline["output"] / ("." + state["target"] + ".pending")
    class Stream:
        def __init__(self, real):
            self.real = real
            state["fd"] = real.fileno()
        def __enter__(self):
            return self
        def __exit__(self, *args):
            try:
                return self.real.__exit__(*args)
            finally:
                state["fd"] = None
                state["steps"].append("close")
                if state["fault"] == "close":
                    raise OSError("private close " + KEY)
        def write(self, raw):
            state["steps"].append("write")
            if state["fault"] in {"write", "short_write"}:
                count = self.real.write(raw[:12])
                if state["fault"] == "write":
                    raise OSError("private write " + KEY)
                return count
            return self.real.write(raw)
        def flush(self):
            state["steps"].append("flush")
            self.real.flush()
            if state["fault"] == "flush":
                raise OSError("private flush " + KEY)
        def fileno(self):
            return self.real.fileno()
    def opened(path, mode="r", *args, **kwargs):
        real = original_open(path, mode, *args, **kwargs)
        return Stream(real) if path in paths() and mode == "xb" else real
    def sync(fd):
        if state["fd"] == fd:
            state["steps"].append("fsync")
            final_path, pending = paths()
            state["at_sync"].append((final_path.exists(), pending.read_bytes()))
            if state["fault"] == "fsync":
                raise OSError("private fsync " + KEY)
        return original_sync(fd)
    def link(source, target):
        if target == paths()[0]:
            state["steps"].append("link")
            assert state["fd"] is None and state["steps"][-2] == "close"
            if state["fault"] == "link":
                raise OSError("private hard link " + KEY)
        return original_link(source, target)
    monkeypatch.setattr(Path, "open", opened)
    monkeypatch.setattr(os, "fsync", sync)
    monkeypatch.setattr(os, "link", link)
    return state


@pytest.mark.parametrize("target", ["identity.json", "experiment_manifest.json", "authorization.json",
                                   "CQ01.json", "CQ02.json", "summary.json"])
def test_publication_occurs_only_after_complete_fsync_and_close(offline, publication_io, target):
    """Setup, case and summary publication all reuse the completed-candidate primitive."""
    publication_io["target"] = target
    summary = batch(offline)
    assert summary["passed"]
    assert publication_io["steps"] == ["write", "flush", "fsync", "close", "link"]
    visible, raw = publication_io["at_sync"][0]
    assert visible is False and (offline["output"] / target).read_bytes() == raw
    assert not (offline["output"] / ("." + target + ".pending")).exists()


@pytest.mark.parametrize("target", ["identity.json", "experiment_manifest.json", "authorization.json",
                                   "CQ01.json", "CQ02.json", "summary.json"])
@pytest.mark.parametrize("fault", ["write", "short_write", "flush", "fsync", "close", "link"])
def test_failed_publication_never_exposes_success_or_allows_next_http(
    offline, publication_io, capsys, target, fault,
):
    """Success-shaped pending bytes cannot pass a failed durability/publication boundary."""
    publication_io.update(target=target, fault=fault)
    assert cli.main(arguments(offline, paid=True)) == 1
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert not result["passed"] and KEY not in captured.out + captured.err
    assert not (offline["output"] / target).exists()
    expected = 2 if target == "CQ01.json" else 4 if target in {"CQ02.json", "summary.json"} else 0
    assert len(offline["requests"]) == expected
    if expected:
        assert result["request_count"] == expected and result["unknown_usage_requests"] == 0
        assert result["stop_reason"] == "persistence_failed"
        assert result["summary_persisted"] is (target != "summary.json")
        assert result["unrun_cases"] == (["CQ02"] if target == "CQ01.json" else [])
        assert Decimal(result["known_usage_estimated_usd"]) > 0
        if fault == "fsync":
            assert json.loads(publication_io["at_sync"][0][1])["passed"] is True


@pytest.mark.parametrize("occupied", ["candidate", "destination"])
def test_publication_never_overwrites_occupied_names(offline, occupied):
    """Even a name occupied after output admission is not replaced or resumed."""
    ledger = canary.CatalogQwenLedger(offline["output"])
    name = ".summary.json.pending" if occupied == "candidate" else "summary.json"
    path = offline["output"] / name
    path.write_bytes(b"preserve existing bytes")
    with pytest.raises(canary.CanaryStopped, match="persistence_failed"):
        canary._publish_result(ledger, "summary.json", {"passed": True})
    assert path.read_bytes() == b"preserve existing bytes" and not offline["requests"]


def test_failed_pending_cleanup_does_not_revoke_published_truth(offline, monkeypatch):
    """Cleanup is optional AFTER publication; a leftover pending name is not resumable."""
    original = Path.unlink
    def fail(path, *args, **kwargs):
        if path == offline["output"] / ".summary.json.pending":
            raise OSError("private cleanup " + KEY)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", fail)
    summary = batch(offline)
    assert summary["passed"] and read_json(offline["output"] / "summary.json") == summary
    assert (offline["output"] / ".summary.json.pending").read_bytes() == (offline["output"] / "summary.json").read_bytes()
