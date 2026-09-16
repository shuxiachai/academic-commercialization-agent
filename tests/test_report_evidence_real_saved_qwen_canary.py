"""RS live boundaries with wholly synthetic packets and intercepted HTTP only."""

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

import report_evidence_real_saved_canary as cli
from academic_agent import report_evidence_real_saved_qwen_canary as canary
from academic_agent.report_evidence_final_json_qwen_canary import _publish_result as frozen_publish

KEY = "sk-rs-fake-offline-not-a-credential"
COMMIT = "a" * 40
REAL_ROOT, REAL_GIT = canary.ROOT, canary._git
USAGE = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
SETUP = ("manifest.json", "identity.json", "experiment_manifest.json", "authorization.json")
PRIVATE = ("RAW_REPORT_LOCAL", "RAW_META_LOCAL", "PRIVATE_LABEL_LOCAL", "PRIVATE_NOTE_LOCAL",
           "PRIVATE_REVIEW_LOCAL", "PRIVATE_PATH_LOCAL")


def encode(value):
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def events(output):
    return [json.loads(line) for line in (output / "events.jsonl").read_text(encoding="utf-8").splitlines()]


def synthetic_files():
    """No private fixture import/read: construct 4/8/8 sources and a 1408-point target."""
    sources = {"topic": "Synthetic material", "failed_domains": {}}
    for group, prefix, count in (("academic", "A", 4), ("patent", "P", 8), ("market", "M", 8)):
        sources[group + "_sources"] = [{
            "source_id": f"{prefix}{index}", "title": f"Synthetic {prefix}{index}",
            "publisher": "Synthetic publisher", "source_type": "synthetic_record",
            "accessed_date": "2020-01-01", "published_date": "2099-01-01",
            "url": f"https://example.invalid/{prefix}{index}", "doi": None,
            "summary_source": "abstract" if group == "academic" else "search_snippet",
            "evidence_summary": f"Saved synthetic content {prefix}{index}",
        } for index in range(1, count + 1)]
    sources["academic_sources"][-1]["evidence_summary"] = "前🙂e\u0301" + "x" * 1404
    metadata = {"topic": sources["topic"], "status": "success", "evidence_mode": "live",
                "note": PRIVATE[1], "path": PRIVATE[-1]}
    questions = [{"case_id": "RS01", "question": "Explain synthetic material result and scope."},
                 {"case_id": "RS02", "question": "Does synthetic material prove vehicle deployment?"}]
    labels = {"private_reference": PRIVATE[2], "cases": [
        {"case_id": case_id, "source_id": "A4", "required_state": state, "require_full_window": True}
        for case_id, state in (("RS01", "answered_with_evidence"), ("RS02", "abstained"))]}
    files = {"commercialization_report.md": PRIVATE[0].encode(), "validated_sources.json": encode(sources),
             "meta.json": encode(metadata), "questions.json": encode(questions),
             "expected.private.json": encode(labels), "reference-notes.md": PRIVATE[3].encode(),
             "reference-review.md": PRIVATE[4].encode(), "offline-probe.json": b'{"synthetic":true}',
             "label-isolation.json": b'{"synthetic":true}'}
    prepared = canary.rs.prepare_inputs(*(files[name] for name in canary.ORIGINAL_FILES), questions)
    binding = canary.rs.bind_inputs(prepared, files["expected.private.json"])
    files["prepared-inputs.json"] = encode(prepared.model_dump(mode="json"))
    files["binding.private.json"] = encode(binding.model_dump(mode="json"))
    manifest = {
        "schema": 1, "protocol": canary.rs.PROTOCOL_IDENTITY, "state": "offline_prepared_not_live_authorized",
        "live_authorization": False, "provider_requests": 0,
        "files_sha256": {name: canary._sha(raw) for name, raw in files.items()},
        "original_bytes_sha256": {name: canary._sha(files[name]) for name in canary.ORIGINAL_FILES},
        "source_files_sha256": {"old_preparation_file": "0" * 64}, "implementation_commit": "b" * 40,
        "runtime": {"python": "historical-not-current"}, "binding_sha256": binding.binding_sha256,
        **{name: getattr(prepared, name) for name in (
            "prepared_sha256", "snapshot_sha256", "catalog_sha256", "questions_sha256",
            "configuration_sha256", "projection_sha256")},
    }
    files[canary.MANIFEST] = encode(manifest)
    return files


def final(ids=(), *, status="answered", answer="Synthetic bounded answer."):
    return {"role": "assistant", "content": json.dumps({
        "answer": answer, "status": status, "evidence_ids": list(ids)})}


def native(source_id="A4", *, offset=0, length=1500, call_id="native_read"):
    return {"role": "assistant", "content": None, "tool_calls": [{
        "id": call_id, "type": "function", "function": {"name": "read_source", "arguments": json.dumps({
            "source_id": source_id, "offset": offset, "length": length})}}]}


def payload(message, **changes):
    return {"model": "qwen3.5-plus", "usage": deepcopy(USAGE), "choices": [{
        "index": 0, "message": message, "finish_reason": "tool_calls" if message.get("tool_calls") else "stop",
    }], **changes}


def response(value, *, status=200, headers=None):
    raw = value if isinstance(value, bytes) else encode(value)
    return httpx.Response(status, stream=httpx.ByteStream(raw), headers=headers)


def provider(request):
    """Receipts come from actual tool bytes, not a fabricated expected receipt."""
    body = json.loads(request.content)
    negative = "vehicle" in body["messages"][1]["content"]
    last = body["messages"][-1]
    if last["role"] != "tool":
        return response(payload(native()))
    delivered = json.loads(last["content"])
    assert delivered["text"] and delivered["stored_length"] == 1408
    return response(payload(final(status="abstained") if negative else final([delivered["evidence_id"]])))


@pytest.fixture(autouse=True)
def offline(tmp_path, monkeypatch):
    """Copy only PUBLIC code; all packet bytes are constructed in this temporary repo."""
    repo, committed = tmp_path / "repo", {}
    for name in canary.IDENTITY_PATHS:
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REAL_ROOT / name, path)
        committed[name] = path.read_bytes().replace(b"\r\n", b"\n")
    (repo / "outputs").mkdir()
    packet_dir = repo / "PRIVATE_PATH_LOCAL"
    packet_dir.mkdir()
    for name, raw in synthetic_files().items():
        (packet_dir / name).write_bytes(raw)
    versions = {row["name"]: row["version"] for row in tomllib.loads(
        (repo / "uv.lock").read_text(encoding="utf-8"))["package"]}
    state = {"repo": repo, "packet": packet_dir, "committed": committed, "versions": versions,
             "git": [], "key_reads": [], "requests": [], "intents": [], "setup": [], "handler": provider,
             "http_options": [], "client_options": [], "output": repo / canary.OUTPUT}

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
        pytest.fail("unexpected git operation")

    class Environment:
        def get(self, name):
            state["key_reads"].append(name)
            assert name == "DASHSCOPE_API_KEY"
            return state.get("key", KEY)

    monkeypatch.setattr(canary, "ROOT", repo)
    monkeypatch.setattr(canary, "MANIFEST_SHA256", canary._sha((packet_dir / canary.MANIFEST).read_bytes()))
    monkeypatch.setattr(canary, "_git", git)
    monkeypatch.setattr(canary, "version", versions.__getitem__)
    monkeypatch.setattr(canary, "os", SimpleNamespace(environ=Environment(), path=os.path))
    real_client = httpx.AsyncClient

    def forbidden(*args, **kwargs):
        pytest.fail("real HTTP forbidden")

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
    args = ["--expected-commit", COMMIT, "--expected-manifest-sha256", canary.MANIFEST_SHA256,
            "--packet-dir", str(state["packet"])]
    return args + (["--authorize-paid", canary.PROTOCOL_IDENTITY] if paid else [])


def batch(state):
    return canary.run_canary(expected_commit=COMMIT, expected_manifest_sha256=canary.MANIFEST_SHA256,
                             packet_dir=state["packet"], authorize_paid=canary.PROTOCOL_IDENTITY)


def packet(state):
    return canary.load_packet(state["packet"], canary.MANIFEST_SHA256)


def no_effects(state):
    assert not state["key_reads"] and not state["requests"]
    assert list((state["repo"] / "outputs").iterdir()) == []


def rebind_manifest(state, monkeypatch, manifest=None):
    """Test-only authorizations let projection/shape tests get past raw-byte checks."""
    path = state["packet"] / canary.MANIFEST
    manifest = read_json(path) if manifest is None else manifest
    manifest["files_sha256"] = {name: canary._sha((state["packet"] / name).read_bytes()) for name in canary.PACKET_FILES}
    manifest["original_bytes_sha256"] = {name: manifest["files_sha256"][name] for name in canary.ORIGINAL_FILES}
    raw = encode(manifest)
    path.write_bytes(raw)
    monkeypatch.setattr(canary, "MANIFEST_SHA256", canary._sha(raw))


def test_identity_cli_never_echoes_private_names_paths_content_or_keys(offline, capsys):
    """Default CLI verifies locally without key lookup, output, HTTP or private identity detail."""
    assert cli.main(arguments(offline)) == 0
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["mode"] == "identity_only" and result["identity_verified"] and not result["live_authorized"]
    identity = canary.verify_identity(COMMIT, canary.MANIFEST_SHA256, offline["packet"])
    assert result["identity_sha256"] == canary._sha(canary._encoded(identity))
    for value in (*PRIVATE, *canary.PACKET_FILES, str(offline["packet"]), KEY):
        assert value not in captured.out + captured.err
    assert set(identity["disk_sha256"]) == set(identity["committed_sha256"]) == set(canary.IDENTITY_PATHS)
    no_effects(offline)


@pytest.mark.parametrize("name", (canary.MANIFEST, *canary.PACKET_FILES))
def test_every_private_byte_binding_is_reloaded_after_a_successful_check(offline, name):
    """A cached prepared object cannot hide later drift in ANY of the eleven raw files."""
    before = packet(offline)
    path = offline["packet"] / name
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(canary.CanaryStopped, match="identity_mismatch"):
        packet(offline)
    assert before.prepared.snapshot.sources[3].stored_length == 1408
    no_effects(offline)


@pytest.mark.parametrize("field", ["report_sha256", "sources_sha256", "metadata_sha256", "questions", "snapshot",
                                  "catalog_json", "configuration_json", "projection_sha256"])
def test_entire_stored_projection_is_compared_not_just_hash_fields(offline, monkeypatch, field):
    """Even authorized changed cache bytes cannot substitute for original-byte reconstruction."""
    path = offline["packet"] / "prepared-inputs.json"
    value = read_json(path)
    if field == "questions":
        value[field][0]["question"] += " changed"
    elif field == "snapshot":
        value[field]["sources"][0]["summary"] += " changed"
    else:
        value[field] = "changed"
    path.write_bytes(encode(value))
    rebind_manifest(offline, monkeypatch)
    with pytest.raises(canary.CanaryStopped, match="packet_projection_mismatch"):
        packet(offline)
    no_effects(offline)


@pytest.mark.parametrize("name", [*canary.ORIGINAL_FILES, "questions.json", "expected.private.json", "binding.private.json"])
def test_originals_and_labels_are_recomputed_against_stored_binding(offline, monkeypatch, name):
    """Matching manifest raw hashes do not waive projection or independent label binding."""
    path = offline["packet"] / name
    if name in canary.ORIGINAL_FILES or name == "expected.private.json":
        path.write_bytes(path.read_bytes() + b"\n")
    else:
        value = read_json(path)
        if name == "questions.json":
            value[0]["question"] += " changed"
        else:
            value["prepared_sha256"] = "0" * 64
        path.write_bytes(encode(value))
    rebind_manifest(offline, monkeypatch)
    with pytest.raises(canary.CanaryStopped, match="packet_(projection|label_binding)_mismatch"):
        packet(offline)
    no_effects(offline)


@pytest.mark.parametrize("field", ["prepared_sha256", "snapshot_sha256", "catalog_sha256", "configuration_sha256",
                                  "questions_sha256", "projection_sha256", "binding_sha256"])
def test_manifest_derived_hashes_do_not_override_reconstruction(offline, monkeypatch, field):
    """Every declared preparation identity must match independently rebuilt data."""
    manifest = read_json(offline["packet"] / canary.MANIFEST)
    manifest[field] = "0" * 64
    rebind_manifest(offline, monkeypatch, manifest)
    with pytest.raises(canary.CanaryStopped, match="packet_derived_identity_mismatch"):
        packet(offline)
    no_effects(offline)


@pytest.mark.parametrize("name", ["../outside", "nested/file", "nested\\file", "C:/outside", "alternate.json"])
def test_manifest_cannot_choose_any_additional_or_traversal_filename(offline, monkeypatch, name):
    """The code whitelist is checked before any manifest-supplied name could be opened."""
    path = offline["packet"] / canary.MANIFEST
    value = read_json(path)
    value["files_sha256"][name] = "0" * 64
    raw = encode(value)
    path.write_bytes(raw)
    monkeypatch.setattr(canary, "MANIFEST_SHA256", canary._sha(raw))
    with pytest.raises(canary.CanaryStopped, match="packet_manifest_invalid"):
        packet(offline)
    no_effects(offline)


@pytest.mark.parametrize("target", ["packet", "ancestor", *canary.PACKET_FILES, canary.MANIFEST, "outputs"])
@pytest.mark.parametrize("kind", ["symlink", "junction"])
def test_all_indirect_paths_fail_before_key_or_dispatch(offline, monkeypatch, target, kind):
    """Portable lstat seam covers both symlinks and Windows reparse-point junctions."""
    selected = (offline["packet"] if target == "packet" else offline["repo"] if target == "ancestor"
                else offline["repo"] / "outputs" if target == "outputs" else offline["packet"] / target)
    original = Path.lstat
    def lstat(path, *args, **kwargs):
        if path == selected:
            return SimpleNamespace(st_mode=stat.S_IFLNK if kind == "symlink" else stat.S_IFDIR,
                                   st_file_attributes=0 if kind == "symlink" else stat.FILE_ATTRIBUTE_REPARSE_POINT)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(canary.CanaryStopped, match="indirect_path_rejected"):
        batch(offline)
    assert not offline["requests"] and not offline["key_reads"]


@pytest.mark.parametrize("kind", ["traversal", "outside", "missing"])
def test_packet_directory_is_lexically_scoped(offline, kind):
    """Resolving away '..' first must not silently admit a forbidden packet path."""
    offline["packet"] = (offline["packet"] / ".." / "PRIVATE_PATH_LOCAL" if kind == "traversal"
                         else offline["repo"].parent if kind == "outside" else offline["repo"] / "missing")
    with pytest.raises(canary.CanaryStopped):
        batch(offline)
    no_effects(offline)


@pytest.mark.parametrize("name", canary.IDENTITY_PATHS)
def test_every_current_import_dependency_hidden_disk_drift_is_rejected(offline, name):
    """A clean/assume-unchanged status cannot bypass fixed-path disk versus git blob checks."""
    path = offline["repo"] / name
    path.write_bytes(path.read_bytes() + b"\n# hidden drift\n")
    with pytest.raises(canary.CanaryStopped, match="committed_content_mismatch"):
        batch(offline)
    no_effects(offline)


@pytest.mark.parametrize("defect", ["commit", "commit_shape", "manifest_authority", "dirty", "git_failure", "blob",
                                  "missing_file", "attributes", "versions", "missing_package"])
def test_current_identity_failures_precede_keys_output_and_http(offline, monkeypatch, capsys, defect):
    """Historical preparation provenance never substitutes for CURRENT version/blob checks."""
    args, git = arguments(offline, paid=True), canary._git
    if defect == "commit":
        args[1] = "b" * 40
    elif defect == "commit_shape":
        args[1] = "HEAD"
    elif defect == "manifest_authority":
        args[3] = "0" * 64
    elif defect in {"dirty", "git_failure"}:
        def changed(*items):
            if defect == "git_failure":
                raise subprocess.CalledProcessError(1, ["git"], stderr=KEY)
            return b" M changed" if items[0] == "status" else git(*items)
        monkeypatch.setattr(canary, "_git", changed)
    elif defect == "blob":
        offline["committed"][canary.PROTOCOL] += b"changed"
    elif defect == "missing_file":
        (offline["repo"] / canary.PROTOCOL).unlink()
    elif defect == "attributes":
        raw = b"* text=auto\n"
        (offline["repo"] / ".gitattributes").write_bytes(raw)
        offline["committed"][".gitattributes"] = raw
    elif defect == "versions":
        offline["versions"]["httpx"] = "0.0.0"
    else:
        def missing(name):
            raise PackageNotFoundError(name)
        monkeypatch.setattr(canary, "version", missing)
    assert cli.main(args) == 1
    assert KEY not in capsys.readouterr().out
    no_effects(offline)


def test_historical_provenance_and_crlf_are_not_current_byte_authority(offline):
    """Historical commit/runtime differences are expected; only current normalized blobs match."""
    name = "src/academic_agent/report_evidence_real_saved_qwen_canary.py"
    path = offline["repo"] / name
    raw = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    path.write_bytes(raw)
    identity = canary.verify_identity(COMMIT, canary.MANIFEST_SHA256, offline["packet"])
    assert identity["disk_sha256"][name] == canary._sha(raw)
    assert identity["disk_sha256"][name] != identity["committed_sha256"][name]
    assert identity["packet"]["preparation_provenance_is_current_code_authority"] is False
    no_effects(offline)


@pytest.mark.parametrize("extra", [["--output-dir", "PRIVATE_PATH_LOCAL"], ["--api-key", KEY],
                                  ["--authorize", KEY], ["--resume"],
                                  ["--authorize-paid", "report_evidence_catalog_qwen_canary_v1"]])
def test_cli_rejects_budget_reset_legacy_and_secret_arguments_without_echo(offline, capsys, extra):
    """No alternate-output, old acknowledgement, resume or credential flag buys authority."""
    if extra[0] == "--authorize-paid":
        assert cli.main(arguments(offline) + extra) == 1
    else:
        with pytest.raises(SystemExit) as exc:
            cli.main(arguments(offline) + extra)
        assert exc.value.code == 2
    captured = capsys.readouterr()
    assert KEY not in captured.out + captured.err and "PRIVATE_PATH_LOCAL" not in captured.out + captured.err
    no_effects(offline)


@pytest.mark.parametrize("key", [None, "", " contains whitespace ", 123, "x" * 513])
def test_key_lookup_is_dedicated_process_only_and_never_falls_back(offline, capsys, key):
    """Invalid process credentials cannot load dotenv or an operator/global fallback."""
    offline["key"] = key
    assert cli.main(arguments(offline, paid=True)) == 1
    assert json.loads(capsys.readouterr().out)["error"] == "invalid_dedicated_key"
    assert offline["key_reads"] == ["DASHSCOPE_API_KEY"] and not offline["requests"]
    assert not offline["output"].exists()


def test_fixed_output_is_exclusive_and_cannot_be_reused(offline):
    """An occupied fixed batch directory is not a resume or a new request allowance."""
    offline["output"].mkdir()
    sentinel = offline["output"] / "existing"
    sentinel.write_bytes(b"preserve")
    with pytest.raises(canary.CanaryStopped, match="output_creation_failed_or_occupied"):
        batch(offline)
    assert sentinel.read_bytes() == b"preserve" and not offline["requests"] and not offline["key_reads"]


def test_four_actual_http_calls_keep_nonempty_rs02_receipt_without_final_ids(offline, capsys):
    """The real executor/adapter/ledger must deliver paired 1408-point text in BOTH cases."""
    assert cli.main(arguments(offline, paid=True)) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["passed"] and summary["request_count"] == len(offline["requests"]) == 4
    assert not summary["unrun_cases"] and summary["unknown_usage_requests"] == 0
    assert summary["semantic_support"] == "not_assessed" and summary["answer_verification"] == "not_verified"
    assert Decimal(summary["budget_consumed_usd"]) == Decimal("0.044597248")
    assert read_json(offline["output"] / "summary.json") == summary
    finished = [event for event in events(offline["output"]) if event["event"] == "request_finished"]
    bound = packet(offline)
    for index, (request, intent, record, setup) in enumerate(zip(
            offline["requests"], offline["intents"], finished, offline["setup"], strict=True)):
        body = json.loads(request.content)
        assert request.content == canary._encoded(body) and len(request.content) <= 12288
        assert intent["event"] == "request_reserved" and intent["request_id"] == index + 1
        assert intent["request_sha256"] == record["request_sha256"] == hashlib.sha256(request.content).hexdigest()
        assert record["request"] == intent["request"] == body and record["reported_usage"] == USAGE
        assert record["usage_status"] == "complete" and record["protocol_accepted"]
        assert record["provider_response_received"] and record["response_model_matches_authorized"]
        assert request.url == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer " + KEY
        assert request.headers["accept-encoding"] == "identity"
        assert body["model"] == "qwen3.5-plus" and body["max_tokens"] == 512 and body["temperature"] == 0
        assert body["enable_thinking"] is body["stream"] is body["parallel_tool_calls"] is False
        assert body["messages"][1]["content"] == bound.prepared.questions[index // 2].question
        catalog = json.loads(body["messages"][2]["content"])
        assert catalog["returned_count"] == catalog["total_count"] == 20 and catalog["coverage"] == "complete"
        assert [row["source_id"] for row in catalog["entries"]] == [s.source_id for s in bound.prepared.snapshot.sources]
        assert all(set(row) == {"source_id", "title", "title_truncated"} for row in catalog["entries"])
        for marker in (*PRIVATE, "required_state", "require_full_window", "expected.private", "reference_source"):
            assert marker not in request.content.decode("ascii")
        if index % 2 == 0:
            assert len(body["messages"]) == 3 and body["tool_choice"] == "auto" and "response_format" not in body
            assert [tool["function"]["name"] for tool in body["tools"]] == ["read_source"]
            assert body["tools"][0]["function"]["parameters"]["properties"]["source_id"]["enum"] == [
                s.source_id for s in bound.prepared.snapshot.sources]
            assert "x" * 100 not in request.content.decode("ascii")
        else:
            assert body["tool_choice"] == "none" and "tools" not in body
            assert body["response_format"] == {"type": "json_object"}
            assert body["messages"][3] == finished[index - 1]["assistant_message"]
            tool = body["messages"][4]
            delivered = json.loads(tool["content"])
            assert tool["role"] == "tool" and tool["tool_call_id"] == "native_read"
            assert delivered["text"] == bound.prepared.snapshot.sources[3].summary
            assert (delivered["start"], delivered["end"], delivered["stored_length"]) == (0, 1408, 1408)
            assert delivered["status"] == "ok" and not delivered["window_truncated"]
        assert setup["manifest.json"]["live_authorization"] is False
        auth, experiment, identity = (setup[name] for name in ("authorization.json", "experiment_manifest.json", "identity.json"))
        assert experiment["scope"] == "parent_only_single_real_saved_live_batch"
        assert auth["expected_manifest_sha256"] == canary.MANIFEST_SHA256 and auth["expected_commit"] == COMMIT
        assert auth["max_requests"] == experiment["configuration"]["max_requests"] == 4
        assert not auth["independent_user_consent_verified"] and auth["parent_operator_only"]
        assert not auth["old_allowance_reused"] and auth["standing_authorization_source"] == canary.PROTOCOL
        assert auth["identity_sha256"] == canary._sha(canary._encoded(identity))
        assert auth["experiment_manifest_sha256"] == canary._sha(canary._encoded(experiment))
    results = [read_json(offline["output"] / (name + ".json"))["result"] for name in canary.rs.CASE_IDS]
    assert results[0]["state"] == "answered_with_evidence" and results[0]["evidence_ids"]
    assert results[1]["state"] == "abstained" and results[1]["evidence_ids"] == []
    for result in results:
        assert len(result["served_evidence"]) == 1 and result["served_evidence"][0]["text"]
        assert result["audit"]["forwarded_read_ids"] == result["audit"]["core"]["delivered_read_ids"]
        assert result["audit"]["core"]["tool_executions"] == 1
    assert offline["http_options"] == [{"retries": 0, "verify": True, "trust_env": False}] * 4
    assert all(options["follow_redirects"] is options["trust_env"] is False and options["verify"] is True
               for options in offline["client_options"])


@pytest.mark.parametrize("defect", ["wrong_source", "partial", "offset", "early_abstain", "early_answer", "invisible"])
def test_first_accounted_reply_stops_before_second_http_without_rewriting_choice(offline, defect):
    """Wrong reference/insufficient window/early termination cannot buy a second HTTP request."""
    message = (final(status="abstained" if defect == "early_abstain" else "answered")
               if defect.startswith("early") else native("A1" if defect == "wrong_source" else
                                                         "A99" if defect == "invisible" else "A4",
                                                         offset=1 if defect == "offset" else 0,
                                                         length=1407 if defect == "partial" else 1500))
    offline["handler"] = lambda _: response(payload(message))
    summary = batch(offline)
    assert len(offline["requests"]) == 1
    assert not summary["passed"] and summary["unrun_cases"] == ["RS02"]
    assert summary["unknown_usage_requests"] == 0 and Decimal(summary["known_usage_estimated_usd"]) > 0
    records = [event for event in events(offline["output"]) if event["event"] == "request_finished"]
    if defect != "invisible":
        assert records[0]["assistant_message"] == message
    assert not (offline["output"] / "RS02.json").exists()


@pytest.mark.parametrize("defect", ["fenced", "prose", "wrong_id", "empty_id", "wrong_state", "final_tool"])
def test_first_case_final_failure_prevents_rs02(offline, defect):
    """Strict final schemas and frozen state/citations cannot be repaired by the runner."""
    def handle(request):
        if len(offline["requests"]) == 1:
            return provider(request)
        delivered = json.loads(json.loads(request.content)["messages"][-1]["content"])
        message = final([delivered["evidence_id"]])
        if defect in {"fenced", "prose"}:
            message["content"] = ("```json\n" + message["content"] + "\n```" if defect == "fenced"
                                  else "Answer: " + message["content"])
        elif defect == "wrong_id":
            message = final(["A4"])
        elif defect == "empty_id":
            message = final()
        elif defect == "wrong_state":
            message = final(status="abstained")
        else:
            message = native(call_id="another_read")
        return response(payload(message))
    offline["handler"] = handle
    summary = batch(offline)
    assert len(offline["requests"]) == 2 and summary["unrun_cases"] == ["RS02"] and not summary["passed"]


@pytest.mark.parametrize("defect", ["early", "wrong_read", "partial", "answered", "cited_abstention"])
def test_rs02_requires_nonempty_read_then_uncited_abstention(offline, defect):
    """RS02 is not the old missing-text case; sensible prose cannot waive its required state."""
    def handle(request):
        if len(offline["requests"]) <= 2:
            return provider(request)
        if len(offline["requests"]) == 3:
            return response(payload(final(status="abstained") if defect == "early" else
                                    native("A1" if defect == "wrong_read" else "A4",
                                           length=12 if defect == "partial" else 1500)))
        receipt = json.loads(json.loads(request.content)["messages"][-1]["content"])
        return response(payload(final([receipt["evidence_id"]], status="answered" if defect == "answered" else "abstained")))
    offline["handler"] = handle
    summary = batch(offline)
    assert len(offline["requests"]) == (3 if defect in {"early", "wrong_read", "partial"} else 4)
    assert not summary["passed"] and summary["cases"][0]["passed"] and not summary["cases"][1]["passed"]


@pytest.mark.parametrize("phase,expected_calls", [(2, 0), (3, 1), (4, 1), (5, 2), (6, 2), (7, 3), (8, 3), (9, 4)])
def test_identity_rechecks_before_and_after_every_callback_retain_usage(offline, monkeypatch, phase, expected_calls):
    """Identity drift at any callback boundary stops later HTTP without erasing known spending."""
    original, calls = canary.verify_identity, []
    def verify(*args):
        calls.append(1)
        result = original(*args)
        if len(calls) == phase:
            result["runtime"]["python"] = "changed"
        return result
    monkeypatch.setattr(canary, "verify_identity", verify)
    summary = batch(offline)
    assert len(offline["requests"]) == summary["request_count"] == expected_calls
    assert not summary["passed"] and summary["stop_reason"] == "runtime_identity_changed"
    assert summary["unknown_usage_requests"] == 0
    assert (Decimal(summary["known_usage_estimated_usd"]) > 0) is bool(expected_calls)


@pytest.mark.parametrize("name", canary.PACKET_FILES)
def test_actual_private_drift_during_first_http_is_not_cached(offline, name):
    """Each raw binding is reread after real dispatch, including notes not sent to the model."""
    def handle(request):
        path = offline["packet"] / name
        path.write_bytes(path.read_bytes() + b"\n")
        return provider(request)
    offline["handler"] = handle
    summary = batch(offline)
    assert len(offline["requests"]) == 1 and summary["stop_reason"] == "packet_file_identity_mismatch"
    assert not summary["passed"] and summary["unknown_usage_requests"] == 0
    assert Decimal(summary["known_usage_estimated_usd"]) > 0


@pytest.mark.parametrize("defect", ["unknown_usage", "contradictory_usage", "wrong_model", "malformed", "secret",
                                  "escaped_secret", "timeout", "redirect", "http_error", "oversize", "compressed"])
def test_transport_failures_keep_usage_reservations_and_redact_diagnostics(offline, capsys, defect):
    """An uncertain or secret-bearing reply is never free, repaired, retried or publicly echoed."""
    def handle(request):
        if len(offline["requests"]) == 1:
            return provider(request)
        if defect == "timeout":
            raise httpx.ReadTimeout("private " + KEY)
        if defect in {"redirect", "http_error"}:
            return response(KEY.encode(), status=302 if defect == "redirect" else 500)
        if defect == "oversize":
            return response(b"x" * 65537)
        if defect == "compressed":
            return response(b"bad", headers={"content-encoding": "gzip"})
        if defect == "malformed":
            return response(b'{invalid "' + KEY.encode())
        value = payload(final(answer=KEY if defect == "secret" else "Encoded: " + "".join(
            f"\\u{ord(char):04x}" for char in KEY) if defect == "escaped_secret" else "Synthetic"))
        if defect == "unknown_usage":
            value.pop("usage")
        elif defect == "contradictory_usage":
            value["usage"]["total_tokens"] = 999
        elif defect == "wrong_model":
            value["model"] = "other-model"
        return response(value)
    offline["handler"] = handle
    assert cli.main(arguments(offline, paid=True)) == 1
    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert len(offline["requests"]) == summary["request_count"] == 2 and summary["unrun_cases"] == ["RS02"]
    unknown = defect not in {"wrong_model", "secret", "escaped_secret"}
    assert summary["unknown_usage_requests"] == int(unknown)
    assert summary["cost_coverage"] == ("lower_bound" if unknown else "complete_for_reported_requests")
    assert Decimal(summary["known_usage_estimated_usd"]) > 0
    assert Decimal(summary["budget_consumed_usd"]) == Decimal("0.022298624")
    assert KEY not in captured.out + captured.err
    assert all(KEY not in path.read_text(encoding="utf-8") for path in offline["output"].iterdir())


@pytest.mark.parametrize("count,first,reason", [(4, 0, "runner_request_limit"), (4, 4, "runner_request_limit"),
                                              (2, 0, "runner_case_request_limit")])
def test_runner_limits_independently_refuse_fresh_transport_dispatch(offline, count, first, reason):
    """The inherited six-request ledger or a new conversation must not widen RS limits."""
    identity = canary.verify_identity(COMMIT, canary.MANIFEST_SHA256, offline["packet"])
    bound = packet(offline)
    ledger = canary.CatalogQwenLedger(offline["output"])
    ledger.records = [{}] * count
    transport = canary.CatalogQwenFollowupTransport(KEY, ledger, snapshot=bound.prepared.snapshot)
    checked = canary._CheckedTransport(transport, ledger, identity, offline["packet"], bound, bound.expected[0], first)
    result = canary.run_catalog_followup(bound.prepared.snapshot, bound.prepared.questions[0].question, transport=checked)
    assert result.state == "failed" and ledger.stop_reason == reason and not offline["requests"]


def test_frozen_cost_cap_refuses_reservation_without_dispatch(offline):
    """The stricter runner ceiling does not bypass the frozen USD 0.10 reservation check."""
    identity = canary.verify_identity(COMMIT, canary.MANIFEST_SHA256, offline["packet"])
    bound = packet(offline)
    ledger = canary.CatalogQwenLedger(offline["output"])
    ledger.records = [{"reservation_usd": "0.095", "estimated_usd": "0.095", "usage_status": "complete"}]
    transport = canary.CatalogQwenFollowupTransport(KEY, ledger, snapshot=bound.prepared.snapshot)
    checked = canary._CheckedTransport(transport, ledger, identity, offline["packet"], bound, bound.expected[0], 1)
    result = canary.run_catalog_followup(bound.prepared.snapshot, bound.prepared.questions[0].question, transport=checked)
    assert result.state == "failed" and ledger.stop_reason == "budget_limit" and not offline["requests"]


@pytest.mark.parametrize("field", ["protocol_accepted", "provider_response_received", "response_model_matches_authorized",
                                 "usage_status", "case_id", "request_sha256", "tool_choice", "tools", "catalog",
                                 "native_id", "tool_pair", "text", "snapshot_hash", "status", "final_envelope"])
def test_case_gate_checks_actual_accounted_native_wire_not_only_callback_audit(offline, monkeypatch, field):
    """A correct local result cannot mask mismatched paired messages or altered HTTP body bytes."""
    original = canary._case_gate
    def gate(bound, index, result, records, ledger):
        if field in {"protocol_accepted", "provider_response_received", "response_model_matches_authorized"}:
            records[-1][field] = False
        elif field == "usage_status":
            records[-1][field] = "unknown"
        elif field == "case_id":
            records[-1][field] = "OTHER"
        elif field == "request_sha256":
            records[-1][field] = "0" * 64
        elif field == "final_envelope":
            records[-1]["assistant_message"] = final(status="abstained")
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
                delivered[field] = "missing_text" if field == "status" else "changed"
                body["messages"][4]["content"] = json.dumps(delivered)
            records[-1]["request_sha256"] = canary._sha(canary._encoded(body))
        return original(bound, index, result, records, ledger)
    monkeypatch.setattr(canary, "_case_gate", gate)
    summary = batch(offline)
    assert len(offline["requests"]) == 2 and not summary["passed"] and summary["unrun_cases"] == ["RS02"]


@pytest.mark.parametrize("fault", ["none", "receipt_lost", "callback", "catalog", "read", "state", "final_ids"])
def test_single_case_mechanics_match_frozen_two_case_gate_without_placeholder(offline, fault):
    """Coupling to frozen offline rules is tested using TWO actual independent executions."""
    assert batch(offline)["passed"]
    bound = packet(offline)
    observed = []
    for index, question in enumerate(bound.prepared.questions):
        result = canary.rs.CaseRehearsal.model_validate_json(json.dumps({
            "case_id": question.case_id, "prepared_sha256": bound.prepared.prepared_sha256,
            "question_sha256": canary.content_hash(question.model_dump()),
            "result": read_json(offline["output"] / (question.case_id + ".json"))["result"],
        }))
        if index == 1 and fault != "none":
            value = result.result
            if fault == "receipt_lost":
                value = value.model_copy(update={"served_evidence": ()})
            elif fault == "state":
                value = value.model_copy(update={"state": "answered_without_evidence"})
            elif fault == "final_ids":
                value = value.model_copy(update={"evidence_ids": (value.served_evidence[0].evidence_id,)})
            else:
                audit = value.audit
                if fault == "callback":
                    audit = audit.model_copy(update={"downstream_calls": 1})
                elif fault == "catalog":
                    audit = audit.model_copy(update={"catalog_hash": "0" * 64})
                else:
                    audit = audit.model_copy(update={"core": audit.core.model_copy(update={"tool_executions": 0})})
                value = value.model_copy(update={"audit": audit})
            result = result.model_copy(update={"result": value})
        observed.append(result)
    reviews = canary.rs.review_mechanics(bound.prepared, tuple(observed),
                                        expected_bytes=(offline["packet"] / "expected.private.json").read_bytes(),
                                        binding=bound.binding)
    for index, result in enumerate(observed):
        assert canary.review_case_mechanics(bound, index, result.result) == reviews[index]
    assert reviews[1].passed is (fault == "none")


@pytest.mark.parametrize("name", ["manifest.json", "events.jsonl", ".identity.json.pending",
                                 ".experiment_manifest.json.pending", ".authorization.json.pending"])
def test_setup_file_failure_prevents_first_post(offline, monkeypatch, capsys, name):
    """Identity and authorization persistence is a precondition, not post-dispatch documentation."""
    opened = Path.open
    def fail(path, *args, **kwargs):
        if path == offline["output"] / name:
            raise OSError("private " + KEY)
        return opened(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", fail)
    assert cli.main(arguments(offline, paid=True)) == 1
    assert not offline["requests"] and KEY not in capsys.readouterr().out


@pytest.mark.parametrize("phase", ["reserve", "finish"])
def test_journal_failure_preserves_known_usage_and_pending_intent(offline, monkeypatch, phase):
    """Failed reserve sends nothing; failed finish keeps observed usage and unresolved intent."""
    opened, writes = Path.open, []
    def fail(path, mode="r", *args, **kwargs):
        if path == offline["output"] / "events.jsonl" and mode == "r+b":
            writes.append(1)
            if len(writes) == (1 if phase == "reserve" else 2):
                raise OSError("private " + KEY)
        return opened(path, mode, *args, **kwargs)
    monkeypatch.setattr(Path, "open", fail)
    summary = batch(offline)
    assert not summary["passed"] and summary["stop_reason"] == "persistence_failed"
    assert len(offline["requests"]) == (0 if phase == "reserve" else 1)
    if phase == "finish":
        assert summary["pending_request_id"] == 1 and summary["unknown_usage_requests"] == 0
        assert Decimal(summary["known_usage_estimated_usd"]) > 0


@pytest.fixture
def publication_io(offline, monkeypatch):
    """Fault the real filesystem seam, not a fake replacement publisher."""
    state = {"target": "summary.json", "fault": None, "steps": [], "fd": None, "at_sync": []}
    opened, sync, link = Path.open, os.fsync, os.link
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
                    raise OSError(KEY)
        def write(self, raw):
            state["steps"].append("write")
            if state["fault"] in {"write", "short_write"}:
                count = self.real.write(raw[:12])
                if state["fault"] == "write":
                    raise OSError(KEY)
                return count
            return self.real.write(raw)
        def flush(self):
            state["steps"].append("flush")
            self.real.flush()
            if state["fault"] == "flush":
                raise OSError(KEY)
        def fileno(self):
            return self.real.fileno()
    def open_file(path, mode="r", *args, **kwargs):
        real = opened(path, mode, *args, **kwargs)
        return Stream(real) if path == paths()[1] and mode == "xb" else real
    def fsync(fd):
        if fd == state["fd"]:
            state["steps"].append("fsync")
            final_path, pending = paths()
            state["at_sync"].append((final_path.exists(), pending.read_bytes()))
            if state["fault"] == "fsync":
                raise OSError(KEY)
        return sync(fd)
    def publish(source, destination):
        if destination == paths()[0]:
            state["steps"].append("link")
            assert state["fd"] is None and state["steps"][-2] == "close"
            if state["fault"] == "link":
                raise OSError(KEY)
        return link(source, destination)
    monkeypatch.setattr(Path, "open", open_file)
    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "link", publish)
    return state


@pytest.mark.parametrize("target", ["identity.json", "experiment_manifest.json", "authorization.json",
                                   "RS01.json", "RS02.json", "summary.json"])
@pytest.mark.parametrize("fault", ["write", "short_write", "flush", "fsync", "close", "link"])
def test_publication_failure_never_exposes_success_or_admits_later_http(offline, publication_io, capsys, target, fault):
    """Incomplete/unsynced/unclosed candidates are not authoritative result files."""
    publication_io.update(target=target, fault=fault)
    assert cli.main(arguments(offline, paid=True)) == 1
    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    expected = 2 if target == "RS01.json" else 4 if target in {"RS02.json", "summary.json"} else 0
    assert len(offline["requests"]) == expected and KEY not in captured.out + captured.err
    assert not summary["passed"] and not (offline["output"] / target).exists()
    if expected:
        assert summary["request_count"] == expected and summary["unknown_usage_requests"] == 0
        assert summary["stop_reason"] == "persistence_failed"
        assert summary["summary_persisted"] is (target != "summary.json")
        assert summary["unrun_cases"] == (["RS02"] if target == "RS01.json" else [])


def test_publication_order_and_no_overwrite(offline, publication_io):
    """The unchanged helper publishes only after write/flush/fsync/close, with exclusive links."""
    assert batch(offline)["passed"]
    assert publication_io["steps"] == ["write", "flush", "fsync", "close", "link"]
    visible, raw = publication_io["at_sync"][0]
    assert not visible and (offline["output"] / "summary.json").read_bytes() == raw
    ledger = object.__new__(canary.CatalogQwenLedger)
    ledger.output_dir, ledger.stop_reason = offline["output"], None
    with pytest.raises(canary.CanaryStopped, match="persistence_failed"):
        canary._publish_result(ledger, "summary.json", {"passed": False})
    assert (offline["output"] / "summary.json").read_bytes() == raw


def test_executing_import_closure_including_publisher_is_bound(offline):
    """Imports execute even when only one helper is used; no hidden old-runner dependency is omitted."""
    assert canary._publish_result is frozen_publish
    pending = ["src/academic_agent/report_evidence_real_saved_qwen_canary.py", "report_evidence_real_saved_canary.py"]
    seen = set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        assert name in canary.IDENTITY_PATHS
        for node in ast.parse((REAL_ROOT / name).read_text(encoding="utf-8")).body:
            if isinstance(node, ast.ImportFrom) and node.module:
                modules = (["academic_agent." + alias.name for alias in node.names]
                           if node.module == "academic_agent" else [node.module])
                pending.extend("src/" + module.replace(".", "/") + ".py" for module in modules
                               if module.startswith("academic_agent."))
    assert "src/academic_agent/report_evidence_guarded_followup.py" in seen
    assert "src/academic_agent/__init__.py" in canary.IDENTITY_PATHS
    no_effects(offline)


def test_git_reader_is_scoped_read_only_and_disables_optional_index_locks(offline, monkeypatch):
    """Fixed blob verification uses no shell, checkout, mutation or unscoped private scan."""
    calls = []
    def invoke(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout=b"ok")
    monkeypatch.setattr(canary, "subprocess", SimpleNamespace(run=invoke))
    assert REAL_GIT("show", COMMIT + ":" + canary.PROTOCOL) == b"ok"
    assert calls == [(["git", "--no-optional-locks", "show", COMMIT + ":" + canary.PROTOCOL],
                      {"cwd": offline["repo"], "capture_output": True, "check": True, "timeout": 10})]


def test_fresh_cli_import_has_no_key_dotenv_output_or_network_side_effects(offline):
    """A fresh interpreter proves import behavior, not an already cached module's claims."""
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
import report_evidence_real_saved_canary
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
