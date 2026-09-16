"""CLQ controls at the real claim wrapper/tool/HTTP/journal boundary, never live."""

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

import report_evidence_claim_canary as cli
from academic_agent import report_evidence_claim_qwen_canary as canary
from academic_agent.report_evidence_claim_qwen_transport import ClaimQwenLedger

KEY = "sk-clq-offline-invented-not-a-credential"
COMMIT = "a" * 40
USAGE = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
REAL_ROOT, REAL_GIT = canary.ROOT, canary._git
SETUP = ("manifest.json", "identity.json", "experiment_manifest.json", "authorization.json")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def events(output):
    return [json.loads(line) for line in (output / "events.jsonl").read_text(encoding="utf-8").splitlines()]


def native(source_id="A1", *, offset=0, length=1500):
    return {"role": "assistant", "content": None, "tool_calls": [{
        "id": "native_read", "type": "function", "function": {"name": "read_source", "arguments": json.dumps({
            "source_id": source_id, "offset": offset, "length": length})}}]}


def final(ids=(), *, relation="supported", answer="Synthetic answer", caveats=None):
    return {"role": "assistant", "content": json.dumps({
        "claim_relation": relation, "answer": answer, "supporting_evidence_ids": list(ids),
        "caveats": ["Only this single bench test was recorded."] if caveats is None else caveats})}


def payload(message, **changes):
    return {"model": "qwen3.5-plus", "usage": deepcopy(USAGE), "choices": [{
        "index": 0, "message": message, "finish_reason": "tool_calls" if message.get("tool_calls") else "stop",
    }], **changes}


def response(value, *, status=200, headers=None):
    raw = value if isinstance(value, bytes) else json.dumps(value).encode("utf-8")
    return httpx.Response(status, stream=httpx.ByteStream(raw), headers=headers)


def provider(request):
    """Scripted labels are test controls; receipt IDs come from actual tool bytes."""
    body = json.loads(request.content)
    last = body["messages"][-1]
    if last["role"] != "tool":
        return response(payload(native()))
    delivered = json.loads(last["content"])
    claim = body["messages"][1]["content"]
    relation = "refuted" if "Meridian-52" in claim else "insufficient" if "Northvale-63" in claim else "supported"
    ids = [] if relation == "insufficient" else [delivered["evidence_id"]]
    answer = {"supported": "The recorded flow was 18 mL/min at 20 C and 50 kPa.",
              "refuted": "The recorded flow was 11 mL/min, not 18, at 20 C and 50 kPa.",
              "insufficient": "Thickness was recorded; flow was not measured."}[relation]
    return response(payload(final(ids, relation=relation, answer=answer)))


@pytest.fixture(autouse=True)
def offline(tmp_path, monkeypatch):
    """Copy public inputs to a test root; intercept HTTP, never replace the adapter."""
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
             "http_options": [], "client_options": [], "output": repo / canary.FIXED_OUTPUT}

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

    class OS:
        environ = Environment()

        def __getattr__(self, name):
            return getattr(os, name)

    monkeypatch.setattr(canary, "ROOT", repo)
    monkeypatch.setattr(canary, "_git", git)
    monkeypatch.setattr(canary, "version", versions.__getitem__)
    monkeypatch.setattr(canary, "os", OS())
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
        # Windows Proactor needs internal sockets. Forbid network transports,
        # not unrelated event-loop socketpair creation.
        if (not isinstance(kwargs.get("transport"), httpx.MockTransport)
                or kwargs.get("trust_env") is not False or kwargs.get("proxy") is not None or kwargs.get("mounts")):
            forbidden()
        return real_client(**kwargs)

    monkeypatch.setattr(httpx, "AsyncHTTPTransport", transport)
    monkeypatch.setattr(httpx, "AsyncClient", client)
    monkeypatch.setattr(httpx, "HTTPTransport", forbidden)
    monkeypatch.setattr(httpx, "Client", forbidden)
    return state


def arguments(*, paid=False):
    args = ["--expected-commit", COMMIT, "--expected-fixture-sha256", canary.FIXTURE_SHA256]
    return args + (["--authorize-paid", canary.PROTOCOL_IDENTITY] if paid else [])


def batch():
    return canary.run_canary(expected_commit=COMMIT, expected_fixture_sha256=canary.FIXTURE_SHA256,
                             authorize_paid=canary.PROTOCOL_IDENTITY)


def no_effects(state):
    assert not state["key_reads"] and not state["requests"]
    assert list((state["repo"] / "outputs").iterdir()) == []


def test_default_identity_mode_has_no_live_effects(offline, capsys):
    """Default success returns before key discovery or any output/HTTP creation."""
    assert cli.main(arguments()) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["mode"] == "identity_only" and result["identity_verified"] is True
    assert result["live_authorized"] is False
    identity = result["identity"]
    assert set(identity["disk_sha256"]) == set(identity["committed_sha256"]) == set(canary.IDENTITY_PATHS)
    assert identity["configuration_sha256"] == hashlib.sha256(canary._encoded(canary.configuration())).hexdigest()
    no_effects(offline)


def test_fresh_import_closure_has_no_key_dotenv_output_or_http(offline):
    """Import safety includes the executed closure, not just an already cached runner."""
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
    if "KEY" in name or name.startswith(("DASHSCOPE", "OPENAI")):
        blocked()
    return original_get(self, name, *args)
os._Environ.get = getenv
pathlib.Path.mkdir = blocked
httpx.AsyncClient = httpx.Client = blocked
socket.create_connection = blocked
import report_evidence_claim_canary
from academic_agent import report_evidence_claim_qwen_canary as runner
assert "dotenv" not in sys.modules
assert not any("guarded_followup" in name or "final_json" in name for name in sys.modules)
for name, module in tuple(sys.modules.items()):
    if name.startswith("academic_agent") and getattr(module, "__file__", None):
        path = pathlib.Path(module.__file__).resolve().relative_to(runner.ROOT).as_posix()
        assert path in runner.IDENTITY_PATHS, path
print("import_only_no_effects")
'''
    env = {name: os.environ[name] for name in ("SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP") if name in os.environ}
    env["PYTHONPATH"] = os.pathsep.join((str(REAL_ROOT), str(REAL_ROOT / "src")))
    process = subprocess.run([sys.executable, "-B", "-c", script], cwd=REAL_ROOT, env=env,
                             capture_output=True, text=True, check=False, timeout=30)
    assert process.returncode == 0, process.stderr
    assert process.stdout.strip() == "import_only_no_effects"
    no_effects(offline)


def test_static_closure_and_exact_ledger_are_bound(offline):
    """Copying tiny helpers must not pull old JQ/guarded runners into this identity."""
    assert canary.ClaimQwenLedger is ClaimQwenLedger
    pending = ["src/academic_agent/report_evidence_claim_qwen_canary.py", "report_evidence_claim_canary.py"]
    seen = set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        assert name in canary.IDENTITY_PATHS
        for node in ast.parse((REAL_ROOT / name).read_text(encoding="utf-8")).body:
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            modules = (["academic_agent." + alias.name for alias in node.names]
                       if node.module == "academic_agent" else [node.module])
            pending.extend("src/" + module.replace(".", "/") + ".py"
                           for module in modules if module.startswith("academic_agent."))
    assert not any("final_json" in name or "guarded_followup" in name for name in seen)
    assert {canary.FIXTURE, canary.PROTOCOL, "pyproject.toml", "uv.lock", ".gitattributes",
            "src/academic_agent/__init__.py", "tests/test_report_evidence_claim_qwen_transport.py",
            "tests/test_report_evidence_claim_qwen_canary.py"} <= set(canary.IDENTITY_PATHS)


@pytest.mark.parametrize("name", canary.IDENTITY_PATHS)
def test_every_hidden_disk_change_blocks_before_key(offline, name):
    """Clean git status (including assume-unchanged) cannot conceal changed blobs."""
    path = offline["repo"] / name
    path.write_bytes(path.read_bytes() + b"\n# hidden edit\n")
    with pytest.raises(canary.CanaryStopped, match="committed_content_mismatch"):
        batch()
    no_effects(offline)


@pytest.mark.parametrize("defect", ["commit", "commit_shape", "fixture_authority", "git_failure", "dirty",
                                  "blob", "missing_file", "attributes", "fixture_bytes", "missing_package"])
def test_identity_failures_precede_side_effects(offline, monkeypatch, defect):
    """A committed protocol, matching disk and available version proof are separate gates."""
    commit, fixture = COMMIT, canary.FIXTURE_SHA256
    git = canary._git
    if defect == "commit":
        commit = "b" * 40
    elif defect == "commit_shape":
        commit = "HEAD"
    elif defect == "fixture_authority":
        fixture = "0" * 64
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
        offline["committed"][name] = raw
    else:
        def unavailable(name):
            raise PackageNotFoundError(name)
        monkeypatch.setattr(canary, "version", unavailable)
    with pytest.raises(canary.CanaryStopped):
        canary.run_canary(expected_commit=commit, expected_fixture_sha256=fixture,
                          authorize_paid=canary.PROTOCOL_IDENTITY)
    no_effects(offline)


@pytest.mark.parametrize("name", canary.DEPENDENCIES)
def test_each_executing_package_version_is_checked(offline, name):
    """Version binding must include transitive HTTP and validation dependencies."""
    offline["versions"][name] = "0.0.0"
    with pytest.raises(canary.CanaryStopped, match="installed_dependency_mismatch"):
        batch()
    no_effects(offline)


def test_lf_comparison_does_not_normalize_fixture_authority(offline):
    """Source CRLF checkout may match LF blobs; the fixture's raw hash must still match."""
    name = "src/academic_agent/report_evidence_claim_qwen_canary.py"
    path = offline["repo"] / name
    raw = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    path.write_bytes(raw)
    identity = canary.verify_identity(COMMIT, canary.FIXTURE_SHA256)
    assert identity["disk_sha256"][name] == hashlib.sha256(raw).hexdigest()
    assert identity["disk_sha256"][name] != identity["committed_sha256"][name]
    fixture = offline["repo"] / canary.FIXTURE
    fixture.write_bytes(fixture.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    with pytest.raises(canary.CanaryStopped, match="fixture_identity_mismatch"):
        batch()
    no_effects(offline)


@pytest.mark.parametrize("defect", ["extra", "order", "target", "relation", "two_sources", "url", "doi",
                                  "empty", "absent", "long_summary", "long_title", "publisher", "claim"])
def test_fixture_validation_is_not_only_a_hash_check(offline, monkeypatch, defect):
    """Even an authorized hash cannot expand this batch's three single-source controls."""
    cases = canary.load_cases()
    case, source = cases[0], cases[0]["sources"][0]
    if defect == "extra":
        case["expected_answer"] = "not input"
    elif defect == "order":
        cases.reverse()
    elif defect == "target":
        case["target_source_id"] = "A2"
    elif defect == "relation":
        case["expected_relation"] = "refuted"
    elif defect == "two_sources":
        case["sources"].append(deepcopy(source))
    elif defect in {"url", "doi"}:
        source[defect] = "invented locator"
    elif defect in {"empty", "absent", "long_summary"}:
        source["summary"] = {"empty": "  ", "absent": None, "long_summary": "x" * 500}[defect]
    elif defect == "long_title":
        source["title"] = "x" * 257
    elif defect == "publisher":
        source["publisher"] = "not synthetic"
    else:
        case["claim"] = ""
    raw = canary._encoded(cases)
    (offline["repo"] / canary.FIXTURE).write_bytes(raw)
    monkeypatch.setattr(canary, "FIXTURE_SHA256", hashlib.sha256(raw).hexdigest())
    with pytest.raises(canary.CanaryStopped, match="fixture_invalid_or_unavailable"):
        canary.load_cases()
    no_effects(offline)


@pytest.mark.parametrize("flag", ["--output-dir", "--force", "--resume", "--case", "--api-key", "--authorize"])
def test_cli_rejects_scope_expansion_without_echo(offline, capsys, flag):
    """No output override, case selection, retry or credential command-line surface."""
    with pytest.raises(SystemExit) as exc:
        cli.main(arguments(paid=True) + [flag, KEY])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert KEY not in captured.out + captured.err
    no_effects(offline)


@pytest.mark.parametrize("value", ["report_evidence_catalog_qwen_canary_v1", KEY, "", None, 1])
def test_only_exact_new_acknowledgement_is_admitted(offline, value):
    """An old allowance or missing/wrong-typed acknowledgement cannot dispatch."""
    with pytest.raises(canary.CanaryStopped, match="fresh_protocol_acknowledgement_required"):
        canary.run_canary(expected_commit=COMMIT, expected_fixture_sha256=canary.FIXTURE_SHA256,
                          authorize_paid=value)
    no_effects(offline)


@pytest.mark.parametrize("key", [None, "", " has whitespace ", 123, "x" * 513])
def test_process_only_key_never_falls_back(offline, capsys, key):
    """Rejected process DASHSCOPE credentials cannot select dotenv or another provider."""
    offline["key"] = key
    assert cli.main(arguments(paid=True)) == 1
    captured = capsys.readouterr()
    assert KEY not in captured.out + captured.err
    assert offline["key_reads"] == ["DASHSCOPE_API_KEY"] and not offline["requests"]
    assert not offline["output"].exists()


@pytest.mark.parametrize("kind", ["empty", "failed_setup", "pending", "file", "missing_parent"])
def test_fixed_output_never_reuses_any_occupied_state(offline, kind):
    """An empty or failed batch directory consumes its name, not just successful output."""
    output = offline["output"]
    if kind == "missing_parent":
        output.parent.rmdir()
    elif kind == "file":
        output.write_bytes(b"preserve")
    else:
        output.mkdir()
        if kind != "empty":
            (output / ("manifest.json" if kind == "failed_setup" else ".summary.json.pending")).write_bytes(b"preserve")
    before = list(output.iterdir()) if output.is_dir() else None
    with pytest.raises(canary.CanaryStopped):
        batch()
    assert not offline["key_reads"] and not offline["requests"]
    if before is not None:
        assert list(output.iterdir()) == before


@pytest.mark.parametrize("place", ["root", "outputs", "output", "source"])
@pytest.mark.parametrize("kind", ["symlink", "reparse"])
def test_indirect_ancestors_and_dangling_output_refuse(offline, monkeypatch, place, kind):
    """lstat, not exists/resolve alone, must reject links including dangling output."""
    target = {"root": offline["repo"], "outputs": offline["output"].parent, "output": offline["output"],
              "source": offline["repo"] / canary.IDENTITY_PATHS[1]}[place]
    original = Path.lstat
    def inspect(path, *args, **kwargs):
        if path == target:
            return SimpleNamespace(st_mode=stat.S_IFLNK if kind == "symlink" else stat.S_IFDIR,
                                   st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT if kind == "reparse" else 0)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "lstat", inspect)
    with pytest.raises(canary.CanaryStopped, match="indirect_path_rejected"):
        batch()
    assert not offline["key_reads"] and not offline["requests"]


def test_output_creation_race_does_not_overwrite_winner(offline, monkeypatch):
    """Admission is advisory; exact ledger mkdir must arbitrate ordinary competition."""
    original = Path.mkdir
    def raced(path, *args, **kwargs):
        if path == offline["output"]:
            original(path)
            (path / "sentinel").write_bytes(b"winner")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "mkdir", raced)
    with pytest.raises(canary.CanaryStopped, match="output_creation_failed_or_occupied"):
        batch()
    assert not offline["requests"] and (offline["output"] / "sentinel").read_bytes() == b"winner"


def test_real_three_cases_six_http_shared_exact_ledger_and_separate_authority(offline, monkeypatch, capsys):
    """Support/refutation/insufficiency use actual complete receipts and one shared journal."""
    ledgers, transports = [], []
    original = canary.ClaimQwenFollowupTransport
    def constructed(*args, **kwargs):
        instance = original(*args, **kwargs)
        transports.append(instance)
        ledgers.append(args[1])
        assert type(args[1]) is ClaimQwenLedger
        return instance
    monkeypatch.setattr(canary, "ClaimQwenFollowupTransport", constructed)
    assert cli.main(arguments(paid=True)) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["request_count"] == len(offline["requests"]) == 6
    assert summary["mechanical_passed"] is summary["label_match_passed"] is True
    assert "passed" not in summary and summary["semantic_review"] == "pending"
    assert len({id(item) for item in ledgers}) == 1 and len({id(item) for item in transports}) == 3
    assert summary["unrun_cases"] == [] and summary["unknown_usage_requests"] == 0
    assert summary["semantic_support"] == "not_assessed" and summary["answer_verification"] == "not_verified"
    assert Decimal(summary["budget_consumed_usd"]) == Decimal("0.066895872")
    assert read_json(offline["output"] / "summary.json") == summary
    finished = [event for event in events(offline["output"]) if event["event"] == "request_finished"]
    cases = canary.load_cases()
    for index, (request, intent, record, setup) in enumerate(zip(
            offline["requests"], offline["intents"], finished, offline["setup"], strict=True)):
        body = json.loads(request.content)
        assert intent["event"] == "request_reserved" and intent["request_id"] == index + 1
        assert request.content == canary._encoded(body)
        assert intent["request_sha256"] == record["request_sha256"] == hashlib.sha256(request.content).hexdigest()
        assert intent["request"] == record["request"] == body
        assert record["reported_usage"] == USAGE and record["usage_status"] == "complete"
        assert record["protocol_accepted"] and record["provider_response_received"]
        assert record["response_model_matches_authorized"] and len(request.content) <= 12288
        assert request.url == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer " + KEY
        assert request.headers["accept-encoding"] == "identity"
        assert b"expected_relation" not in request.content and b"target_source_id" not in request.content
        assert body["messages"][1] == {"role": "user", "content": cases[index // 2]["claim"]}
        assert body["model"] == "qwen3.5-plus" and body["max_tokens"] == 512 and body["temperature"] == 0
        assert body["enable_thinking"] is body["stream"] is body["parallel_tool_calls"] is False
        catalog = json.loads(body["messages"][2]["content"])
        assert catalog["returned_count"] == catalog["total_count"] == 1
        assert catalog["coverage"] == "complete" and catalog["entries"][0]["source_id"] == "A1"
        if index % 2 == 0:
            assert len(body["messages"]) == 3 and body["tool_choice"] == "auto" and "response_format" not in body
            assert body["tools"][0]["function"]["parameters"]["properties"]["source_id"]["enum"] == ["A1"]
            assert cases[index // 2]["sources"][0]["summary"] not in request.content.decode()
        else:
            assert body["tool_choice"] == "none" and "tools" not in body
            assert body["response_format"] == {"type": "json_object"}
            assert body["messages"][3] == finished[index - 1]["assistant_message"]
            delivered = json.loads(body["messages"][4]["content"])
            assert body["messages"][4]["tool_call_id"] == "native_read"
            assert delivered["status"] == "ok" and delivered["text"] == cases[index // 2]["sources"][0]["summary"]
        assert setup["manifest.json"]["live_authorization"] is False
        assert setup["manifest.json"]["scope"] == "offline_contract_no_live_authorization"
        experiment, auth, identity = (setup[name] for name in SETUP[2:] + ("identity.json",))
        assert experiment["configuration"]["max_requests"] == auth["max_requests"] == 6
        assert experiment["configuration"]["max_requests_per_case"] == 2
        assert experiment["configuration"]["usd_soft_limit"] == "0.10"
        assert experiment["scope"] == "parent_only_single_synthetic_live_batch"
        assert experiment["adapter_manifest_grants_live_authorization"] is False
        assert auth["independent_user_consent_verified"] is False and auth["parent_operator_only"] is True
        assert auth["old_allowance_reused"] is False and auth["standing_authorization_source"] == canary.PROTOCOL
        assert auth["identity_sha256"] == hashlib.sha256(canary._encoded(identity)).hexdigest()
        assert auth["experiment_manifest_sha256"] == hashlib.sha256(canary._encoded(experiment)).hexdigest()
    for index, case in enumerate(cases):
        outcome = read_json(offline["output"] / (case["case_id"] + ".json"))
        result = outcome["result"]
        assert outcome["mechanical_passed"] is outcome["label_match_passed"] is True and "passed" not in outcome
        assert outcome["semantic_review"] == "pending" and result["claim"] == case["claim"]
        assert result["model_assessment"]["claim_relation"] == case["expected_relation"]
        assert result["state"] == ("abstained" if index == 2 else "answered_with_evidence")
        assert result["read_status"] == "usable_text" and len(result["served_evidence"]) == 1
        audit = result["audit"]
        assert audit["delivered_read_ids"] == audit["usable_read_ids"] == audit["catalog"]["forwarded_read_ids"]
        assert audit["delivered_read_ids"] == audit["catalog"]["core"]["delivered_read_ids"]
        assert result["model_assessment"]["supporting_evidence_ids"] == ([] if index == 2 else audit["usable_read_ids"])
        assert json.loads(finished[index * 2 + 1]["assistant_message"]["content"]) == result["model_assessment"]
    assert offline["http_options"] == [{"retries": 0, "verify": True, "trust_env": False}] * 6
    assert all(options["follow_redirects"] is options["trust_env"] is False and options["verify"] is True
               and options["timeout"].connect == 10 and options["timeout"].read == 60
               for options in offline["client_options"])
    assert set(path.name for path in offline["output"].iterdir()) == {*SETUP, "events.jsonl", "summary.json",
                                                                 "CLQ01.json", "CLQ02.json", "CLQ03.json"}


@pytest.mark.parametrize("defect", ["old_schema", "empty_receipt", "forged_receipt", "unavailable", "extra_field"])
def test_wrapper_failure_after_transport_acceptance_stops_actual_http(offline, defect):
    """Two accepted ledger rows cannot buy CLQ02 when the real claim wrapper refuses."""
    def handle(request):
        body = json.loads(request.content)
        if len(offline["requests"]) != 2:
            return provider(request)
        receipt = json.loads(body["messages"][-1]["content"])["evidence_id"]
        declaration = json.loads(final([receipt])["content"])
        if defect == "old_schema":
            declaration = {"answer": "Old envelope", "status": "answered", "evidence_ids": [receipt]}
        elif defect in {"empty_receipt", "forged_receipt"}:
            declaration["supporting_evidence_ids"] = [] if defect == "empty_receipt" else ["ev_forged"]
        elif defect == "unavailable":
            declaration.update(claim_relation="unavailable", supporting_evidence_ids=[])
        else:
            declaration["status"] = "answered"
        return response(payload({"role": "assistant", "content": json.dumps(declaration)}))
    offline["handler"] = handle
    summary = batch()
    # Mutation-sensitive: check actual HTTP first, not merely a summary flag.
    assert len(offline["requests"]) == 2
    assert summary["unrun_cases"] == ["CLQ02", "CLQ03"] and not summary["mechanical_passed"]
    assert summary["label_match_passed"] is None and summary["semantic_review"] == "not_reviewable"
    assert summary["unknown_usage_requests"] == 0
    rows = [row for row in events(offline["output"]) if row["event"] == "request_finished"]
    assert len(rows) == 2 and all(row["protocol_accepted"] for row in rows)
    result = read_json(offline["output"] / "CLQ01.json")["result"]
    assert result["state"] == "failed" and result["model_assessment"] is None


@pytest.mark.parametrize("case_index,relation", [(0, "refuted"), (0, "insufficient"), (1, "supported"), (2, "supported")])
def test_legal_label_mismatch_stops_actual_http(offline, case_index, relation):
    """A structurally admitted but differently labeled claim is not a batch pass."""
    def handle(request):
        if len(offline["requests"]) != 2 * case_index + 2:
            return provider(request)
        body = json.loads(request.content)
        receipt = json.loads(body["messages"][-1]["content"])["evidence_id"]
        return response(payload(final([] if relation == "insufficient" else [receipt], relation=relation)))
    offline["handler"] = handle
    summary = batch()
    assert len(offline["requests"]) == 2 * case_index + 2
    outcome = summary["cases"][case_index]
    assert outcome["mechanical_passed"] is True and outcome["label_match_passed"] is False
    assert outcome["semantic_review"] == "pending" and outcome["gate_failure"] == "expected_relation_mismatch"
    assert summary["label_match_passed"] is False and not summary["mechanical_passed"]
    assert summary["unrun_cases"] == list(canary.CASE_IDS[case_index + 1:])
    assert summary["unknown_usage_requests"] == 0


@pytest.mark.parametrize("defect", ["partial", "offset", "wrong_source", "no_read", "refusal"])
def test_first_native_read_failure_preserves_usage_and_never_dispatches_second(offline, defect):
    """Do not spend another paid turn repairing partial/wrong reads or early finals."""
    message = native("A2" if defect == "wrong_source" else "A1",
                     offset=1 if defect == "offset" else 0, length=8 if defect == "partial" else 1500)
    if defect == "no_read":
        message = final(relation="unavailable")
    elif defect == "refusal":
        message = {"role": "assistant", "refusal": "Cannot answer"}
    offline["handler"] = lambda request: response(payload(message))
    summary = batch()
    assert len(offline["requests"]) == summary["request_count"] == 1
    assert summary["unknown_usage_requests"] == 0 and Decimal(summary["known_usage_estimated_usd"]) > 0
    assert summary["label_match_passed"] is None and summary["unrun_cases"] == ["CLQ02", "CLQ03"]
    assert not summary["mechanical_passed"]


@pytest.mark.parametrize("defect", ["receipt_loss", "text", "claim", "wrapper_state", "claim_audit", "catalog_audit", "core_audit"])
def test_gate_checks_full_receipt_original_claim_and_all_audit_layers(offline, monkeypatch, defect):
    """A real completed HTTP pair must not hide post-wrapper delivery/state loss."""
    original = canary.claim_policy.run_claim_relation_followup
    def damaged(*args, **kwargs):
        result = original(*args, **kwargs)
        if defect == "receipt_loss":
            return result.model_copy(update={"served_evidence": ()})
        if defect == "text":
            receipt = result.served_evidence[0].model_copy(update={"text": "forged text"})
            return result.model_copy(update={"served_evidence": (receipt,)})
        if defect in {"claim", "wrapper_state"}:
            return result.model_copy(update={"claim": "different proposition"} if defect == "claim" else {"state": "failed"})
        audit = result.audit
        if defect == "claim_audit":
            audit = audit.model_copy(update={"usable_read_ids": ()})
        elif defect == "catalog_audit":
            audit = audit.model_copy(update={"catalog": audit.catalog.model_copy(update={"forwarded_read_ids": ()})})
        else:
            core = audit.catalog.core.model_copy(update={"terminal_reason": "transport_failed"})
            audit = audit.model_copy(update={"catalog": audit.catalog.model_copy(update={"core": core})})
        return result.model_copy(update={"audit": audit})
    monkeypatch.setattr(canary.claim_policy, "run_claim_relation_followup", damaged)
    summary = batch()
    assert len(offline["requests"]) == 2
    assert not summary["mechanical_passed"] and summary["label_match_passed"] is None
    assert summary["unrun_cases"] == ["CLQ02", "CLQ03"]


@pytest.mark.parametrize("defect", ["journal", "accounting"])
def test_gate_rejects_inconsistent_accounting_observations(offline, monkeypatch, defect):
    """Unmatched persisted rows or invalid usage must fail the accounting gate."""
    original = canary._case_gate
    def damaged(case, snapshot, result, records, ledger):
        if defect == "journal":
            path = ledger.output_dir / "events.jsonl"
            path.write_bytes(path.read_bytes().replace(b'"event":"request_finished"', b'"event":"other"', 1))
        else:
            records[-1]["reported_usage"]["prompt_tokens"] = True
        return original(case, snapshot, result, records, ledger)
    monkeypatch.setattr(canary, "_case_gate", damaged)
    summary = batch()
    assert len(offline["requests"]) == 2 and not summary["mechanical_passed"]
    assert summary["unrun_cases"] == ["CLQ02", "CLQ03"]
    assert summary["cases"][0]["gate_failure"] == "transport_observation_failed"


@pytest.mark.parametrize("defect,reason", [
    ("tool_pair", "full_read_receipt_failed"),
    ("request_hash", "claim_wire_observation_failed"),
    ("native_final", "native_assessment_failed"),
])
def test_late_wire_gates_reject_consistent_journal_tampering(offline, monkeypatch, defect, reason):
    """Each late check must reject independently of accounting and callback sizes.

    The original tests changed only memory, so the journal comparison masked
    these gates. Deliberately corrupt the TEMP test journal consistently too;
    this is fault injection after real HTTP, never a production repair path.
    """
    original = canary._case_gate
    observations = []
    def damaged(case, snapshot, result, records, ledger):
        if case["case_id"] != "CLQ01":
            return original(case, snapshot, result, records, ledger)
        baseline = original(case, snapshot, result, records, ledger)
        row = records[-1]
        if defect == "tool_pair":
            message = row["request"]["messages"][4]
            # Same-size ID keeps both measured callback lengths valid; a
            # recomputed hash keeps the unrelated wire-hash check valid too.
            assert len(message["tool_call_id"]) == len("native_fake")
            message["tool_call_id"] = "native_fake"
            row["request_sha256"] = hashlib.sha256(canary._encoded(row["request"])).hexdigest()
        elif defect == "request_hash":
            row["request_sha256"] = "0" * 64
        else:
            declaration = json.loads(row["assistant_message"]["content"])
            declaration["answer"] = "A different native answer about this single bench test."
            # Keep the four-field schema, actual relation and valid receipt:
            # only the native-declaration/result equality is now false.
            canary.claim_policy.ClaimAssessment.model_validate(declaration)
            row["assistant_message"]["content"] = json.dumps(declaration)
        journal = events(ledger.output_dir)
        for index, event in enumerate(journal):
            if event.get("request_id") != row["request_id"]:
                continue
            if event["event"] == "request_reserved":
                for field in ("request_id", "case_id", "request", "request_sha256", "reservation_usd"):
                    event[field] = deepcopy(row[field])
            elif event["event"] == "request_finished":
                journal[index] = {"event": "request_finished", **deepcopy(row)}
        (ledger.output_dir / "events.jsonl").write_bytes(
            b"".join(canary._encoded(event) + b"\n" for event in journal))
        accounting = canary._check_accounting(case, records, ledger)
        gate_reason = original(case, snapshot, result, records, ledger)
        observations.append((baseline, accounting, gate_reason))
        return gate_reason
    monkeypatch.setattr(canary, "_case_gate", damaged)
    summary = batch()
    # Removing the corresponding late check must buy actual extra HTTP, not
    # merely change an exception category or fail an earlier accounting check.
    assert len(offline["requests"]) == 2
    assert observations == [(None, True, reason)]
    assert summary["cases"][0]["gate_failure"] == summary["stop_reason"] == reason
    assert read_json(offline["output"] / "CLQ01.json")["gate_failure"] == reason
    assert not summary["mechanical_passed"] and summary["label_match_passed"] is None
    assert summary["unknown_usage_requests"] == 0 and summary["unrun_cases"] == ["CLQ02", "CLQ03"]


@pytest.mark.parametrize("when", ["before_first", "after_first", "before_second", "after_second"])
@pytest.mark.parametrize("drift", ["disk", "version", "commit"])
def test_identity_is_checked_before_and_after_every_request(offline, monkeypatch, when, drift):
    """Post-response drift retains known usage; between-turn drift buys no next HTTP."""
    original = canary.verify_identity
    count = 0
    trigger = {"before_first": 2, "after_first": 3, "before_second": 4, "after_second": 5}[when]
    def checking(*args):
        nonlocal count
        count += 1
        if count == trigger:
            if drift == "disk":
                path = offline["repo"] / canary.PROTOCOL
                path.write_bytes(path.read_bytes() + b"hidden")
            elif drift == "version":
                offline["versions"]["httpx"] = "0.0.0"
            else:
                git = canary._git
                monkeypatch.setattr(canary, "_git", lambda *items: b"b" * 40 if items[0] == "rev-parse" else git(*items))
        return original(*args)
    monkeypatch.setattr(canary, "verify_identity", checking)
    summary = batch()
    expected = 0 if when == "before_first" else 2 if when == "after_second" else 1
    assert summary["request_count"] == len(offline["requests"]) == expected
    assert summary["unknown_usage_requests"] == 0 and not summary["mechanical_passed"]
    assert summary["unrun_cases"] == ["CLQ02", "CLQ03"]
    if expected:
        assert Decimal(summary["known_usage_estimated_usd"]) > 0


@pytest.mark.parametrize("defect", ["status", "encoding", "oversize", "read_error", "usage", "model"])
def test_transport_errors_keep_unknown_distinct_and_stop_batch(offline, defect):
    """Non-200/read failures are unknown-cost, never a zero-cost successful case."""
    class Broken(httpx.AsyncByteStream):
        async def __aiter__(self):
            raise httpx.ReadError("private " + KEY)
            yield b""  # pragma: no cover -- defines the asynchronous iterator protocol.
    def handler(request):
        if defect == "read_error":
            return httpx.Response(200, stream=Broken())
        if defect == "oversize":
            return response(b"x" * 65537)
        return response(payload(native(), **({"usage": None} if defect == "usage" else
                                             {"model": "wrong-model"} if defect == "model" else {})),
                        status=503 if defect == "status" else 200,
                        headers={"content-encoding": "gzip"} if defect == "encoding" else None)
    offline["handler"] = handler
    summary = batch()
    assert len(offline["requests"]) == 1 and summary["request_count"] == 1
    assert summary["unknown_usage_requests"] == (0 if defect == "model" else 1)
    assert Decimal(summary["budget_consumed_usd"]) == Decimal("0.011149312")
    assert not summary["mechanical_passed"] and summary["unrun_cases"] == ["CLQ02", "CLQ03"]
    assert KEY not in json.dumps(summary)


@pytest.mark.parametrize("kind", ["overall", "case", "pending", "stopped"])
def test_checked_dispatch_limits_precede_adapter_and_http(offline, kind):
    """Runner limits are checked before delegation, not after a seventh/third POST."""
    ledger = ClaimQwenLedger(offline["output"])
    case = canary.load_cases()[0]
    identity = canary.verify_identity(COMMIT, canary.FIXTURE_SHA256)
    count = 6 if kind == "overall" else 2 if kind == "case" else 0
    ledger.records[:] = [{}] * count
    if kind == "pending":
        ledger.pending = 1
    if kind == "stopped":
        ledger.stop_reason = "already_stopped"
    calls = []
    checked = canary._CheckedTransport(lambda **kw: calls.append(kw), ledger, identity, 0,
                                       case, canary.snapshot_for(case))
    with pytest.raises(canary.CanaryStopped):
        checked(messages=[], tools=[], tool_choice="auto")
    assert not calls and not offline["requests"]


@pytest.mark.parametrize("target", ["manifest.json", "events.jsonl", "request_reserved", "request_finished"])
def test_ledger_setup_and_journal_fsync_failures_halt(offline, monkeypatch, target):
    """Setup/reservation errors cannot dispatch; failed finish keeps unresolved usage."""
    original_open, original_sync = Path.open, os.fsync
    tracked = {}
    def opened(path, mode="r", *args, **kwargs):
        stream = original_open(path, mode, *args, **kwargs)
        if path.parent == offline["output"] and mode in {"xb", "r+b"}:
            tracked[stream.fileno()] = (path, mode)
        return stream
    def sync(fd):
        entry = tracked.pop(fd, None)
        if entry:
            path, mode = entry
            if (target == path.name and mode == "xb" or target.startswith("request_") and mode == "r+b"
                    and json.loads(path.read_text(encoding="utf-8").splitlines()[-1])["event"] == target):
                raise OSError("private fsync " + KEY)
        return original_sync(fd)
    monkeypatch.setattr(Path, "open", opened)
    monkeypatch.setattr(os, "fsync", sync)
    if target in {"manifest.json", "events.jsonl"}:
        with pytest.raises(canary.CanaryStopped):
            batch()
    else:
        summary = batch()
        assert not summary["mechanical_passed"] and summary["stop_reason"] == "persistence_failed"
        if target == "request_finished":
            assert summary["pending_request_id"] == 1 and summary["unknown_usage_requests"] == 0
            assert Decimal(summary["known_usage_estimated_usd"]) > 0
    assert len(offline["requests"]) == (1 if target == "request_finished" else 0)
    assert offline["output"].exists()
    with pytest.raises(canary.CanaryStopped, match="output_creation_failed_or_occupied"):
        batch()


@pytest.fixture
def publication_io(offline, monkeypatch):
    """JQ-derived durability fault harness, targeting only new CLQ publication names."""
    state = {"target": "CLQ01.json", "fault": None, "fd": None, "steps": [], "at_sync": []}
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
            if state["fault"] == "short_write":
                return self.real.write(raw[:12])
            return self.real.write(raw)
        def flush(self):
            state["steps"].append("flush")
            self.real.flush()
        def fileno(self):
            return self.real.fileno()
    def opened(path, mode="r", *args, **kwargs):
        real = original_open(path, mode, *args, **kwargs)
        return Stream(real) if path == paths()[1] and mode == "xb" else real
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
                raise OSError("private link " + KEY)
        return original_link(source, target)
    monkeypatch.setattr(Path, "open", opened)
    monkeypatch.setattr(os, "fsync", sync)
    monkeypatch.setattr(os, "link", link)
    return state


@pytest.mark.parametrize("target", ["identity.json", "experiment_manifest.json", "authorization.json",
                                   "CLQ01.json", "CLQ02.json", "CLQ03.json", "summary.json"])
def test_complete_result_is_published_only_after_fsync_close(offline, publication_io, target):
    """Setup/case/summary files are all invisible until complete write/fsync/close/link."""
    publication_io["target"] = target
    summary = batch()
    assert summary["mechanical_passed"] and summary["label_match_passed"]
    assert publication_io["steps"] == ["write", "flush", "fsync", "close", "link"]
    visible, raw = publication_io["at_sync"][0]
    assert visible is False and (offline["output"] / target).read_bytes() == raw
    assert not (offline["output"] / ("." + target + ".pending")).exists()


@pytest.mark.parametrize("target", ["identity.json", "experiment_manifest.json", "authorization.json",
                                   "CLQ01.json", "CLQ02.json", "CLQ03.json", "summary.json"])
@pytest.mark.parametrize("fault", ["short_write", "fsync", "close", "link"])
def test_publication_failure_never_buys_next_http(offline, publication_io, capsys, target, fault):
    """A success-shaped pending file cannot authorize continuation or become final truth."""
    publication_io.update(target=target, fault=fault)
    assert cli.main(arguments(paid=True)) == 1
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert not result["mechanical_passed"] and KEY not in captured.out + captured.err
    assert not (offline["output"] / target).exists()
    expected = {"CLQ01.json": 2, "CLQ02.json": 4, "CLQ03.json": 6, "summary.json": 6}.get(target, 0)
    assert len(offline["requests"]) == expected
    if expected:
        assert result["request_count"] == expected and result["unknown_usage_requests"] == 0
        assert result["stop_reason"] == "persistence_failed"
        assert result["summary_persisted"] is (target != "summary.json")
        assert result["unrun_cases"] == list(canary.CASE_IDS[expected // 2:])
        assert Decimal(result["known_usage_estimated_usd"]) > 0


@pytest.mark.parametrize("occupied", ["candidate", "destination"])
def test_publication_refuses_occupied_name(offline, occupied):
    """A file racing result publication must be preserved, never replaced."""
    ledger = ClaimQwenLedger(offline["output"])
    name = ".summary.json.pending" if occupied == "candidate" else "summary.json"
    path = offline["output"] / name
    path.write_bytes(b"preserve")
    with pytest.raises(canary.CanaryStopped, match="persistence_failed"):
        canary._publish_result(ledger, "summary.json", {"mechanical_passed": True})
    assert path.read_bytes() == b"preserve" and not offline["requests"]


def test_cli_never_echoes_even_canary_exception_text(offline, monkeypatch, capsys):
    """A typed dependency exception is not permission to expose arbitrary text."""
    def failed(*args, **kwargs):
        raise canary.CanaryStopped(KEY)
    monkeypatch.setattr(cli, "verify_identity", failed)
    assert cli.main(arguments()) == 1
    captured = capsys.readouterr()
    assert KEY not in captured.out + captured.err
    no_effects(offline)


def test_git_reader_is_bounded_read_only(offline, monkeypatch):
    """Identity verification may neither refresh the index nor run a shell command."""
    seen = []
    def invoked(command, **kwargs):
        seen.append((command, kwargs))
        return SimpleNamespace(stdout=b"ok")
    monkeypatch.setattr(canary, "subprocess", SimpleNamespace(run=invoked))
    assert REAL_GIT("show", COMMIT + ":" + canary.PROTOCOL) == b"ok"
    assert seen == [(["git", "--no-optional-locks", "show", COMMIT + ":" + canary.PROTOCOL],
                     {"cwd": offline["repo"], "capture_output": True, "check": True, "timeout": 10})]
